from jav_downloader.web import file_stream


def test_parse_range_suffix():
    assert file_stream._parse_range("bytes=0-99", 1000) == (0, 99)


def test_parse_range_open_end():
    assert file_stream._parse_range("bytes=500-", 1000) == (500, 999)
