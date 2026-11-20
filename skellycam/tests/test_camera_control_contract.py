def test_reads_never_stop_or_pause_cameras(client, mock_camera_group_manager):
    """sfn26 contract, with Q495 of the user: no request pauses the cameras; a GET does not stop a take."""
    assert client.get('/skellycam/camera/group/all/record/stop').status_code == 405
    for method in ('get', 'put', 'post'):
        assert getattr(client, method)('/skellycam/camera/group/all/pause').status_code == 404
    assert client.get('/skellycam/camera/group/all/pause_unpause').status_code == 404
    mock_camera_group_manager.stop_recording_all_groups.assert_not_awaited()
