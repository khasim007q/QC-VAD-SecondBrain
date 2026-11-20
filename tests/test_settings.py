from classnotes.settings import Settings


def test_new_settings_defaults():
    s = Settings()
    assert (s.audio_output, s.playback_rate, s.stop_after_line, s.theme) == ("", 1.0, False, "system")
