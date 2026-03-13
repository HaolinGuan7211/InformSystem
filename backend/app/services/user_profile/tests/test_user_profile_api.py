from __future__ import annotations


def test_user_profile_api_supports_manual_upsert_and_readback(
    api_client,
    load_user_profile_mock,
) -> None:
    payload = load_user_profile_mock(
        "upstream_inputs",
        "graduation_material_submission__input__manual_profile_request.json",
    )
    expected = load_user_profile_mock(
        "downstream_outputs",
        "graduation_material_submission__output__user_profile.json",
    )

    put_response = api_client.put("/api/v1/users/stu_001/profile", json=payload)
    get_response = api_client.get("/api/v1/users/stu_001/profile")

    assert put_response.status_code == 200
    assert put_response.json()["profile"] == expected
    assert get_response.status_code == 200
    assert get_response.json()["profile"] == expected


def test_list_active_users_endpoint_respects_limit(
    api_client,
    load_user_profile_mock,
) -> None:
    graduation_payload = load_user_profile_mock(
        "upstream_inputs",
        "graduation_material_submission__input__manual_profile_request.json",
    )
    course_payload = load_user_profile_mock(
        "upstream_inputs",
        "course_schedule_change__input__manual_profile_request.json",
    )

    api_client.put("/api/v1/users/stu_001/profile", json=graduation_payload)
    api_client.put("/api/v1/users/stu_002/profile", json=course_payload)
    response = api_client.get("/api/v1/users/active?limit=1")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert len(response.json()["users"]) == 1
