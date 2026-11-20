from unittest.mock import call


def test_reads_never_stop_or_toggle_cameras(client, mock_camera_group_manager):
    assert client.get('/skellycam/camera/group/all/record/stop').status_code == 405
    assert client.get('/skellycam/camera/group/all/pause').status_code == 405
    assert client.get('/skellycam/camera/group/all/pause_unpause').status_code == 404
    mock_camera_group_manager.stop_recording_all_groups.assert_not_awaited()
    mock_camera_group_manager.set_paused_all_groups.assert_not_awaited()


def test_pause_requests_are_explicit_and_repeatable(client, mock_camera_group_manager):
    for desired in (True, True, False, False):
        response = client.put('/skellycam/camera/group/all/pause', json={'paused': desired})
        assert response.status_code == 200
        assert response.json() == {'paused': desired}
    assert mock_camera_group_manager.set_paused_all_groups.await_args_list == [
        call(paused=value) for value in (True, True, False, False)]
    for body in ({}, {'paused': 'false'}, {'paused': 1}):
        assert client.put('/skellycam/camera/group/all/pause', json=body).status_code == 422
    assert mock_camera_group_manager.set_paused_all_groups.await_count == 4
