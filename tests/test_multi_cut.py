from jav_downloader.sites import multi_cut


class DummySite:
    pass


def test_multicut_workdir_is_stable_per_job(tmp_path):
    site = DummySite()
    site._web_job_id = "job-abc"
    dest = str(tmp_path)

    first = multi_cut._multicut_workdir(site, dest, "jav-hlsmulticut-")
    second = multi_cut._multicut_workdir(site, dest, "jav-hlsmulticut-")

    assert first == second
    assert first.endswith("jav-hlsmulticut-job-abc")
    assert site._multicut_workdir == first


def test_discard_multicut_workdir_only_on_cancel():
    site = DummySite()
    site._pause_job = True
    site._cancel_job = False
    assert multi_cut._discard_multicut_workdir(site) is False

    site._cancel_job = True
    assert multi_cut._discard_multicut_workdir(site) is True
