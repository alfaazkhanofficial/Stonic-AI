"""EchoGuard against synthetic rooms. These prove the algorithm separates a copy of
what was played from an independent voice in simulated rooms; they cannot prove
your actual room, which is what scripts/voicelive-calibrate.py is for."""
import numpy as np
import pytest

from stonic.voicelive.echo import EchoGuard, band_power, pcm_level
from voicelive_synth import ROOMS, SR_IN, simulate, speech_like

WARM = 1.6   # seconds of playback before we judge


def rates(records, after=WARM):
    echo = [r for r in records if r[0] > after and not r[2]]
    user = [r for r in records if r[2] and r[0] > 0]
    return (sum(r[1] for r in echo) / max(1, len(echo)), sum(r[1] for r in user) / max(1, len(user)), len(echo), len(user))


@pytest.mark.parametrize("room", ["desk", "laptop"])
def test_own_echo_is_dropped_and_a_second_voice_is_heard(room):
    guard = EchoGuard()
    records = simulate(guard, room, seconds=8.0, user_from=4.5, user_level=1.0)
    # Judge the user only once the smoothing window has filled with their speech.
    settled = [r for r in records if r[2] and r[0] > 4.5 + 0.35]
    false_voice, _, n_echo, _ = rates([r for r in records if r[0] < 4.5])
    detected = sum(r[1] for r in settled) / len(settled)
    assert n_echo > 20
    assert false_voice <= 0.03, f"echo mistaken for a voice {false_voice:.0%}"
    assert detected >= 0.6, f"only {detected:.0%} of a same-loudness second voice was heard"
    assert guard.calibrated and guard.reliable


@pytest.mark.parametrize("room", ["desk", "laptop"])
def test_a_louder_voice_is_reliably_heard(room):
    guard = EchoGuard()
    records = simulate(guard, room, seconds=8.0, user_from=4.5, user_level=1.6)
    settled = [r for r in records if r[2] and r[0] > 4.5 + 0.35]
    assert sum(r[1] for r in settled) / len(settled) >= 0.85


def _sustained_flags(guard):
    """Wrap a guard so we can see, per microphone block, whether ITS OWN sustained-voice bar (what triggers a barge-in) is met."""
    seen = []
    real = guard.is_user_speech

    def spy(pcm, sr, when=None):
        result = real(pcm, sr, when)
        seen.append((when, guard.sustained))
        return result
    guard.is_user_speech = spy
    return seen


@pytest.mark.parametrize("room", ["desk", "laptop", "reverberant", "noisy"])
def test_echo_alone_never_reaches_the_sustained_bar_that_triggers_a_barge_in(room):
    """The safety property for interrupting: across rooms and seeds, a whole reply's worth of
    pure echo must never satisfy the guard's own sustained-voice bar."""
    for seed in (1, 2, 3, 4):
        guard = EchoGuard()
        seen = _sustained_flags(guard)
        simulate(guard, room, seconds=10.0, seed=seed)
        bad = [w for w, ok in seen if ok and w >= WARM]
        assert not bad, f"{room} seed {seed}: echo satisfied the interrupt bar at t={bad[0]:.2f}"


def test_the_pause_tolerance_is_only_used_where_the_microphone_cannot_hear_the_speakers():
    ROOMS["phones"] = dict(atten=0.004, delay=0.05, eq={100: 0, 8000: 0}, reverb=0, noise=0.0005)
    try:
        isolated, room = EchoGuard(), EchoGuard()
        simulate(isolated, "phones", seconds=6.0)
        simulate(room, "noisy", seconds=6.0)
        assert isolated._coupling < 0.05 <= room._coupling
    finally:
        ROOMS.pop("phones", None)


@pytest.mark.parametrize("room", ["desk", "laptop", "reverberant", "noisy"])
def test_a_real_second_voice_does_reach_the_sustained_bar_quickly(room):
    for seed in (1, 2, 3):
        guard = EchoGuard()
        run, reached = 0, None
        for when, flag, _ in simulate(guard, room, seconds=9.0, user_from=6.0, user_level=1.3, seed=seed):
            if when < 6.0:
                continue
            run = run + 1 if flag else 0
            if run >= guard.required_blocks and reached is None:
                reached = when - 6.0
        assert reached is not None and reached < 1.6, f"{room} seed {seed}: voice not recognised in time ({reached})"


def test_reliability_flag_follows_how_high_the_room_forces_the_bar():
    guard = EchoGuard()
    guard._head = 0.10
    assert guard.reliable and guard.required_blocks == 6
    guard._head = 0.30
    assert not guard.reliable and guard.required_blocks == 10


def _sustained_after(room: str, user_from: float, level: float, seed: int, seconds: float = 9.0):
    """Seconds from the user starting to speak until the guard's own 'sustained voice' evidence bar is met."""
    guard = EchoGuard()
    hits = []
    real = guard.is_user_speech

    def spy(pcm, sr, when=None):
        result = real(pcm, sr, when)
        hits.append((when, guard.sustained))
        return result
    guard.is_user_speech = spy
    simulate(guard, room, seconds=seconds, user_from=user_from, user_level=level, seed=seed)
    start = hits[0][0]
    reached = [w - start - user_from for w, ok in hits if ok and w - start >= user_from]
    return (reached[0] if reached else None), guard


def test_headphones_produce_no_false_voice_and_a_person_is_still_heard():
    ROOMS["phones"] = dict(atten=0.004, delay=0.05, eq={100: 0, 8000: 0}, reverb=0, noise=0.0005)
    try:
        guard = EchoGuard()
        assert not any(r[1] for r in simulate(guard, "phones", seconds=5.0))
        assert guard.calibrated and guard.reliable      # "the microphone hears nothing back" is a finished calibration
        for seed in (1, 2, 3):
            reached, _ = _sustained_after("phones", 6.0, 100, seed)
            assert reached is not None and reached < 2.0, f"seed {seed}: a person wearing headphones was not recognised ({reached})"
    finally:
        ROOMS.pop("phones", None)


def test_natural_pauses_between_words_do_not_restart_the_voice_evidence_in_a_quiet_room():
    ROOMS["phones"] = dict(atten=0.004, delay=0.05, eq={100: 0, 8000: 0}, reverb=0, noise=0.0005)
    try:
        # The synthetic talker has syllable-sized dips: without pause tolerance the run never reaches the bar.
        assert all(_sustained_after("phones", 6.0, 80, seed)[0] is not None for seed in (1, 2, 3, 4))
    finally:
        ROOMS.pop("phones", None)


def test_a_long_stretch_of_talking_over_the_playback_does_not_wipe_what_was_learned():
    guard = EchoGuard()
    simulate(guard, "desk", seconds=12.0, user_from=3.0, user_level=1.6)     # ~9 s of a person talking over playback
    assert guard.calibrated and len(guard._residuals) >= 16


def test_static_speaker_colouring_is_learned_not_mistaken_for_a_voice():
    """A laptop speaker with almost no bass: the same echo, tilted. Learning the tilt keeps the floor low."""
    guard = EchoGuard()
    simulate(guard, "laptop", seconds=6.0)
    assert guard.floor < 0.06
    assert float(np.abs(guard._log_gain).max()) > 0.3     # it really did learn a colouring


def test_the_bar_is_learned_from_echo_only_so_a_talker_cannot_raise_it():
    guard = EchoGuard()
    simulate(guard, "desk", seconds=8.0, user_from=3.0, user_level=1.5)
    quiet = EchoGuard()
    simulate(quiet, "desk", seconds=8.0)
    assert guard.threshold <= quiet.threshold * 1.8


def test_with_nothing_playing_any_audible_sound_is_the_user():
    guard = EchoGuard()
    loud = (speech_like(0.2, 3, sr=SR_IN) * 9000).astype(np.int16)[:1024]
    assert guard.is_user_speech(loud, SR_IN, when=1.0) is True
    assert guard.is_user_speech(np.zeros(1024, dtype=np.int16), SR_IN, when=1.1) is False


def test_runs_of_voice_are_counted_and_sustained_needs_several_blocks():
    guard = EchoGuard()
    simulate(guard, "desk", seconds=8.0, user_from=4.5, user_level=1.6)
    assert guard.required_blocks == 6


def test_a_room_that_changes_is_relearned_instead_of_calling_echo_a_voice_forever():
    guard = EchoGuard()
    simulate(guard, "desk", seconds=5.0)
    floor_before = guard.threshold
    # Volume jumps and the colouring changes: the old model no longer explains the echo.
    ROOMS["moved"] = dict(atten=0.9, delay=0.20, eq={100: -20, 500: 6, 2000: -12, 8000: 6}, reverb=0.0, noise=0.004)
    try:
        records = simulate(guard, "moved", seconds=16.0, seed=1)
    finally:
        ROOMS.pop("moved", None)
    tail = [r for r in records if r[0] > 13.0]
    assert sum(r[1] for r in tail) / len(tail) <= 0.2
    assert floor_before > 0


def test_guard_never_raises_on_garbage_input():
    guard = EchoGuard()
    guard.note_output(np.array([1, 2, 3]), 24000)
    guard.note_output(None, 24000)
    assert guard.is_user_speech(np.array([]), 16000) is False
    assert guard.is_user_speech("nonsense", 16000) is False


def test_levels_and_band_power_are_sane():
    silence = np.zeros(1024, dtype=np.int16)
    tone = (np.sin(2 * np.pi * 1000 * np.arange(1024) / 16000) * 8000).astype(np.int16)
    assert pcm_level(silence) == 0.0 and 0.0 < pcm_level(tone) <= 1.0
    bands = band_power(tone, 16000)
    assert int(np.argmax(bands)) == 2      # the 700-1100 Hz band
    assert band_power(tone[:10], 16000).sum() == 0.0
