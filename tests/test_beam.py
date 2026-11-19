import numpy as np
import pytest

from src.core.beam import BeamConfig, LinearBeamSimulator


def test_consistent_mass_modes_and_analytical_beam_frequencies():
    beam = LinearBeamSimulator()
    np.testing.assert_allclose(beam.modes.T @ beam.mass @ beam.modes, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(beam.frequencies_hz, beam.analytical_frequencies_hz(), rtol=.001)
    assert np.all(beam.full_modes[[0, 40]] == 0)
    finer = LinearBeamSimulator(BeamConfig(elements=40))
    assert np.max(abs(finer.frequencies_hz/finer.analytical_frequencies_hz()-1)) < np.max(abs(beam.frequencies_hz/beam.analytical_frequencies_hz()-1))


def test_global_and_local_stiffness_reductions():
    base = LinearBeamSimulator()
    changed = LinearBeamSimulator(uniform_reduction=.6)
    np.testing.assert_allclose(changed.frequencies_hz/base.frequencies_hz, np.sqrt(.4), rtol=1e-8)
    local = LinearBeamSimulator(element_reductions={5: .5})
    assert np.all(local.frequencies_hz < base.frequencies_hz)
    assert np.ptp(local.frequencies_hz/base.frequencies_hz) > .001


def test_sdof_free_decay_matches_closed_form():
    beam = LinearBeamSimulator(BeamConfig(modes=1))
    f = np.zeros((42, 1001))
    result = beam.simulate(f, initial_modal_displacement=[1.0])
    t = result.time_s
    z = beam.config.damping_ratio
    w = beam.omega_rad_s[0]; wd = w*np.sqrt(1-z*z)
    expected = np.exp(-z*w*t)*(np.cos(wd*t)+z*w/wd*np.sin(wd*t))
    np.testing.assert_allclose(result.modal_displacement[0], expected, atol=1e-12)
    energy = .5*(result.modal_velocity[0]**2 + w*w*result.modal_displacement[0]**2)
    assert np.max(np.diff(energy)) < 1e-10


def test_exact_zoh_time_refinement_and_physical_amplitude_scaling():
    beam = LinearBeamSimulator()
    force = beam.nodal_forces(1000, seed=1)
    coarse = beam.simulate(force)
    fine = beam.simulate(np.repeat(force, 2, axis=1), fs_hz=200)
    np.testing.assert_allclose(coarse.modal_displacement, fine.modal_displacement[:, ::2], atol=1e-13)
    np.testing.assert_allclose(coarse.acceleration_m_s2, fine.acceleration_m_s2[:, ::2], atol=1e-11)
    doubled = beam.simulate(2*force)
    np.testing.assert_allclose(doubled.acceleration_m_s2, 2*coarse.acceleration_m_s2, atol=1e-12)
    np.testing.assert_array_equal(force, beam.nodal_forces(1000, seed=1))
    np.testing.assert_array_equal(coarse.acceleration_m_s2, beam.simulate(force).acceleration_m_s2)


def test_noise_is_separate_and_seeded_and_shapes_interpolate():
    beam = LinearBeamSimulator()
    force = beam.nodal_forces(1000)
    clean = beam.simulate(force)
    noisy = beam.simulate(force, noise_std_m_s2=.01)
    np.testing.assert_array_equal(noisy.acceleration_m_s2, beam.simulate(force, noise_std_m_s2=.01).acceleration_m_s2)
    assert np.std(noisy.acceleration_m_s2-clean.acceleration_m_s2) == pytest.approx(.01, rel=.05)
    shapes = beam.sensor_mode_shapes([0, 2.3, 10, 20])
    np.testing.assert_allclose(shapes[[0, 3]], 0, atol=1e-15)
    assert abs(shapes[2, 1]) < 1e-12  # Second mode is unobservable at midspan.


@pytest.mark.parametrize('kwargs', [{'uniform_reduction': 1}, {'element_reductions': {20: .1}}, {'element_reductions': {0: -1}}])
def test_invalid_mechanics_rejected(kwargs):
    with pytest.raises(ValueError):
        LinearBeamSimulator(**kwargs)


def test_invalid_sampling_and_forces_rejected():
    beam = LinearBeamSimulator()
    with pytest.raises(ValueError, match='Sampling'):
        beam.simulate(beam.nodal_forces(100), fs_hz=20)
    force = beam.nodal_forces(100); force[1, 0] = 1
    with pytest.raises(ValueError, match='moments'):
        beam.simulate(force)
