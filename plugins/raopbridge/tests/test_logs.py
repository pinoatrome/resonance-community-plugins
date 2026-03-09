from unittest import mock

from raopbridge.logs import RaopLogsEntry, tail


class TestLogsEntry:
    def test_parse(self, logs_entry_raw_factory):
        expected = 'msg'
        raw = logs_entry_raw_factory(msg=expected)
        actual = RaopLogsEntry.parse(raw)
        assert actual.msg == expected

    def test_repr(self, logs_entry_raw_factory):
        expected = logs_entry_raw_factory()
        actual = RaopLogsEntry.parse(expected).__str__()
        assert actual == expected


class TestRaopLogsReader:

    def test_read_last_lines(self, logs_reader_factory, logs_entry_factory):
        expected = logs_entry_factory()
        line = str(expected)
        reader = logs_reader_factory()
        with mock.patch('raopbridge.logs.tail', return_value=[line]) as mocked:
            [actual] = reader.read_last_lines()
            assert mocked.called
        assert actual == expected


class TestTail:

    def test_tail_little_file(self, file_pointer_factory, logs_entry_raw_factory):
        fp = file_pointer_factory(dim=1, lines=[logs_entry_raw_factory()])
        lines_read = tail(fp)
        assert len(lines_read) == 1

    def test_tail_big_file(self, file_pointer_factory, logs_entry_raw_factory):
        fp = file_pointer_factory(dim=256, lines=[logs_entry_raw_factory()] * 256)
        lines_read = tail(fp, 50, 128)
        assert len(lines_read) == 50

    def test_tail_short_file(self, file_pointer_factory, logs_entry_raw_factory):
        fp = file_pointer_factory(dim=134, lines=[logs_entry_raw_factory()] * 10)
        lines_read = tail(fp, 50, 128)
        assert len(lines_read) == 10


