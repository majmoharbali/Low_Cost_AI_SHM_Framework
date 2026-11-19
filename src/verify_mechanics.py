"""Run a finite numerical verification experiment and write its evidence as JSON."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from .core.beam import LinearBeamSimulator
from .identification import identify_modes, modal_assurance
from .records import SignalWindow, assess_availability


def verify():
    beam = LinearBeamSimulator()
    reference = beam.analytical_frequencies_hz()
    relative_error = abs(beam.frequencies_hz/reference-1)
    reduction = LinearBeamSimulator(uniform_reduction=.6)
    scaling_error = float(np.max(abs(reduction.frequencies_hz/beam.frequencies_hz-np.sqrt(.4))))
    force = beam.nodal_forces(1000, seed=42)
    response = beam.simulate(force)
    finer = beam.simulate(np.repeat(force, 2, axis=1), fs_hz=200)
    time_error = float(np.max(abs(response.acceleration_m_s2-finer.acceleration_m_s2[:, ::2])))
    # Controlled periodic pulses verify pole recovery; not ambient field validation.
    pulse = np.zeros((42, 65536)); pulse[12, ::2048] = 10000.
    result = beam.simulate(pulse)
    w = SignalWindow(result.acceleration_m_s2[:, 8192:], 100., ('S0','S1','S2'), 'controlled-pulse',
                     datetime(2000,1,1,tzinfo=timezone.utc), 'beam_verification')
    bands = [(.9*f, 1.1*f) for f in beam.frequencies_hz]
    modes = identify_modes(w, bands, now=w.end_at)
    shapes = beam.sensor_mode_shapes([2,10,18])
    modal_results = [{
        'status': mode.status, 'frequency_hz': mode.frequency_hz,
        'absolute_error_hz': None if mode.frequency_hz is None else float(abs(mode.frequency_hz-beam.frequencies_hz[i])),
        'mac_to_known_shape': None if mode.shape is None else modal_assurance(mode.shape, shapes[:,i]),
        'reason': mode.reason,
    } for i, mode in enumerate(modes)]
    mid = SignalWindow(w.samples[1:2], 100., ('midspan',), 'nodal-check', w.acquired_at, 'beam_verification')
    unobservable = identify_modes(mid, [bands[1]], now=mid.end_at)[0]
    # Record limited-record stochastic ambiguity honestly, without making it a pass requirement.
    random = beam.simulate(beam.nodal_forces(24000, node_ids=(4,9,15), seed=7))
    random_w = SignalWindow(random.acceleration_m_s2[:,4000:], 100., ('S0','S1','S2'), 'random-check', w.acquired_at, 'beam_verification')
    random_modes = identify_modes(random_w, bands, now=random_w.end_at)
    checks = {
        'analytical_frequencies_below_0_1_percent': bool(relative_error.max() < .001),
        'uniform_stiffness_scaling': scaling_error < 1e-8,
        'zoh_time_refinement': time_error < 1e-9,
        'controlled_fdd_within_one_bin': all(m['absolute_error_hz'] is not None and m['absolute_error_hz'] <= 100/4096 for m in modal_results),
        'nodal_mode_unavailable': unobservable.status == 'unavailable',
        'detector_unfitted': assess_availability(w, now=w.end_at).score is None,
    }
    root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        dirty = bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    return {
        'status': 'passed' if all(checks.values()) else 'failed',
        'scope': 'Numerical verification only; no measured-data, safety, damage-detection or hardware validation',
        'source_revision': revision, 'working_tree_modified': dirty,
        'source_sha256': {str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted((root/'src').rglob('*.py')) if 'legacy' not in p.parts},
        'config': asdict(beam.config), 'checks': checks,
        'frequencies_hz': beam.frequencies_hz.tolist(), 'analytical_hz': reference.tolist(),
        'relative_frequency_errors': relative_error.tolist(),
        'uniform_stiffness_ratio_max_error': scaling_error, 'time_refinement_max_error_m_s2': time_error,
        'fdd': {'excitation':'periodic nodal pulses, 10000 N for 0.01 s every 20.48 s; initial 81.92 s discarded',
                'search_bands_hz': bands, 'nperseg':4096, 'window':'hann', 'overlap':.5,
                'resolution_hz':100/4096, 'controlled_modes':modal_results,
                'midspan_second_mode':unobservable.status,
                'random_record_modes':[{'status':m.status,'frequency_hz':m.frequency_hz,'reason':m.reason} for m in random_modes],
                'limitation':'Model-informed bands; plain FDD assumes suitable excitation and isolated modal peaks. No damping estimate.'},
        'detector': asdict(assess_availability(w,now=w.end_at)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('outputs/verification.json'))
    args = parser.parse_args(argv)
    evidence = verify()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':evidence['status'],'checks':evidence['checks'],'output':str(args.output)},indent=2))
    return 0 if evidence['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
