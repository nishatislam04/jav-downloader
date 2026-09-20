from jav_downloader.web.progress_phase import phase_from_log


def test_phase_from_clip_download():
    parsed = phase_from_log('Clip 2: downloading segments…')
    assert parsed == ('Downloading', 'Clip 2 · segments')


def test_phase_from_encoding():
    parsed = phase_from_log(
        'Encoding… H.264 CRF 28 · 480p · slow · 16 thread(s)')
    assert parsed == (
        'Encoding',
        'H.264 CRF 28 · 480p · slow · 16 thread(s)',
    )


def test_phase_strips_timestamp():
    parsed = phase_from_log('[2:15:20 PM] Found 1436 segments')
    assert parsed == ('Segments found', '1436')


def test_phase_from_retry_round():
    parsed = phase_from_log('Retrying round 2 · 14 segments left')
    assert parsed == ('Retrying', 'Round 2 · 14 left')


def test_phase_from_reusing_segments():
    parsed = phase_from_log('Reusing 120 already-downloaded segments')
    assert parsed == ('Reusing segments', '120')


def test_phase_from_fetching_thumbnail():
    parsed = phase_from_log('Fetching thumbnail…')
    assert parsed == ('Fetching thumbnail', '')


def test_phase_from_saving_as():
    parsed = phase_from_log('Saving as Title [0100-0230].mp4')
    assert parsed == ('Saving', 'Title [0100-0230].mp4')
