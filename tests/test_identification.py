from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from scipy import signal

from src.core.beam import LinearBeamSimulator
from src.records import SignalWindow, assess_availability
from src.identification import identify_modes, welch_matrix, modal_assurance


def window(samples, **kwargs):
    values = np.asarray(samples)
    params = dict(fs_hz=100., sensor_ids=tuple(f'S{i}' for i in range(len(values))), window_id='test',
                  acquired_at=datetime(2000,1,1,tzinfo=timezone.utc), source_kind='beam_verification')
    params.update(kwargs)
    return SignalWindow(values, **params)


def test_welch_cross_spectral_matrix_and_known_shapes():
    t = np.arange(12000)/100
    a, b = np.array([1., .3, -.4]), np.array([.2, -.8, 1.])
    w = window(a[:, None]*np.sin(2*np.pi*5*t)+b[:, None]*np.sin(2*np.pi*12*t))
    spec = welch_matrix(w, nperseg=2048)
    np.testing.assert_allclose(spec.density, spec.density.conj().transpose(0,2,1), atol=1e-14)
    _, reference = signal.welch(w.samples[0], fs=100, nperseg=2048)
    np.testing.assert_allclose(spec.density[:,0,0].real, reference, atol=1e-14)
    found = identify_modes(w, [(4,6), (11,13)], now=w.end_at, nperseg=2048)
    for result, frequency, shape in zip(found, [5,12], [a,b]):
        assert result.status == 'identified'
        assert abs(result.frequency_hz-frequency) <= spec.resolution_hz
        assert modal_assurance(result.shape, shape) > .99


def test_beam_fdd_and_midspan_unobservable_second_mode():
    beam = LinearBeamSimulator()
    # Controlled periodic pulses test pole recovery; not ambient field validation.
    force = np.zeros((42,65536)); force[12,::2048] = 10000
    response = beam.simulate(force)
    w = window(response.acceleration_m_s2[:, 8192:])
    bands = [(f*.9, f*1.1) for f in beam.frequencies_hz]
    modes = identify_modes(w, bands, now=w.end_at)
    for result, f in zip(modes, beam.frequencies_hz):
        assert result.status == 'identified', result.reason
        assert abs(result.frequency_hz-f) <= 100/4096
    middle = window(w.samples[1:2])
    mode2 = identify_modes(middle, [bands[1]], now=middle.end_at)[0]
    assert mode2.status == 'unavailable'
    assert mode2.frequency_hz is None


def test_limited_stochastic_record_can_abstain_on_competing_peaks():
    beam = LinearBeamSimulator()
    response = beam.simulate(beam.nodal_forces(24000, node_ids=(4,9,15), seed=7))
    w = window(response.acceleration_m_s2[:,4000:])
    result = identify_modes(w, [(f*.9,f*1.1) for f in beam.frequencies_hz], now=w.end_at)
    # Platform arithmetic may move a boundary case; every ambiguity must omit its estimate.
    for m in result:
        assert m.status in ('identified','ambiguous','unavailable')
        if m.status != 'identified':
            assert m.frequency_hz is None and m.shape is None


@pytest.mark.parametrize('kind', ['missing', 'nan', 'stale', 'future'])
def test_unavailable_data_never_produce_estimates_or_scores(kind):
    samples = np.zeros((2,1000)); quality = ('valid','valid')
    if kind == 'missing': quality = ('valid','missing')
    if kind == 'nan': samples[0,0] = np.nan
    w = window(samples, quality=quality)
    now = w.end_at + timedelta(seconds=30 if kind == 'stale' else -1 if kind == 'future' else 0)
    result = assess_availability(w, now=now)
    assert result.status != 'not_fitted'
    assert result.score is None and result.threshold is None
    estimates = identify_modes(w, [(4,6)], now=now, nperseg=256)
    assert estimates[0].status == 'unavailable' and estimates[0].frequency_hz is None


def test_unfitted_and_required_missing_sensor_and_copy_semantics():
    data = np.ones((1,100)); w = window(data)
    data[0,0] = np.nan
    assert np.isfinite(w.samples).all()
    assert not w.samples.flags.writeable
    assert assess_availability(w, now=w.end_at).status == 'not_fitted'
    missing = assess_availability(w, now=w.end_at, required_ids=['S0','S1'])
    assert missing.status == 'insufficient_data' and missing.coverage == .5


def test_ambiguous_peaks_and_zero_signal_and_short_record():
    t = np.arange(12000)/100
    w = window(np.array([np.sin(2*np.pi*5*t)+np.sin(2*np.pi*6*t)]))
    result = identify_modes(w, [(4,7)], now=w.end_at, nperseg=1000)[0]
    assert result.status == 'ambiguous' and result.frequency_hz is None
    w = window(np.zeros((1,12000)))
    assert identify_modes(w, [(4,7)], now=w.end_at)[0].status == 'unavailable'
    short = window(np.zeros((1,100)))
    assert identify_modes(short, [(4,7)], now=short.end_at)[0].status == 'unavailable'


def test_window_configuration_validation():
    with pytest.raises(ValueError, match='timezone'):
        window(np.zeros((1,10)), acquired_at=datetime(2000,1,1))
    with pytest.raises(ValueError, match='Convert'):
        window(np.zeros((1,10)), units='g')
