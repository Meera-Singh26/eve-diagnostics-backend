def test_only_admin_can_create(client, user_headers, admin_headers):
    body = {"name": "Eve Andheri", "city": "Mumbai", "address": "12 Link Road"}
    assert client.post("/centres/", json=body).status_code == 401
    assert client.post("/centres/", json=body, headers=user_headers).status_code == 403
    assert client.post("/tests/", json={"name": "CBC"}, headers=user_headers).status_code == 403
    assert client.post("/centres/", json=body, headers=admin_headers).status_code == 201


def test_create_centre_with_tests_and_read_back(client, admin_headers):
    centre = client.post(
        "/centres/",
        json={"name": "Eve Indiranagar", "city": "Bengaluru", "address": "80 Feet Road"},
        headers=admin_headers,
    ).json()
    test = client.post("/tests/", json={"name": "HbA1c"}, headers=admin_headers).json()

    res = client.post(
        f"/centres/{centre['id']}/tests", json={"test_id": test["id"], "price": "450.50"}, headers=admin_headers
    )
    assert res.status_code == 201
    offering = res.json()["offerings"][0]
    assert offering["test"]["name"] == "HbA1c"
    assert offering["price"] == "450.50"

    assert client.get(f"/centres/{centre['id']}").json()["offerings"][0]["price"] == "450.50"


def test_duplicate_centre_test_and_offering(client, admin_headers, catalog):
    dup_centre = {"name": "eve andheri", "city": "MUMBAI", "address": "elsewhere"}
    assert client.post("/centres/", json=dup_centre, headers=admin_headers).status_code == 409
    assert client.post("/tests/", json={"name": "lipid profile"}, headers=admin_headers).status_code == 409

    res = client.post(
        f"/centres/{catalog['centre_id']}/tests",
        json={"test_id": catalog["test_id"], "price": "100"},
        headers=admin_headers,
    )
    assert res.status_code == 409


def test_offering_validation(client, admin_headers, catalog):
    url = f"/centres/{catalog['centre_id']}/tests"
    assert client.post(url, json={"test_id": catalog["test_id"], "price": "-5"}, headers=admin_headers).status_code == 422
    assert client.post(url, json={"test_id": 9999, "price": "10"}, headers=admin_headers).status_code == 404
    assert client.post("/centres/9999/tests", json={"test_id": 1, "price": "10"}, headers=admin_headers).status_code == 404


def test_centre_filters_and_pagination(client, admin_headers, catalog):
    for i in range(3):
        client.post(
            "/centres/",
            json={"name": f"Centre {i}", "city": "Pune", "address": "Some street"},
            headers=admin_headers,
        )
    everything = client.get("/centres/").json()
    assert everything["total"] == 4

    page = client.get("/centres/?limit=2&offset=2").json()
    assert len(page["items"]) == 2 and page["total"] == 4

    assert client.get("/centres/?city=pune").json()["total"] == 3
    by_test = client.get(f"/centres/?test_id={catalog['test_id']}").json()
    assert by_test["total"] == 1 and by_test["items"][0]["name"] == "Eve Andheri"

    assert client.get("/centres/?limit=0").status_code == 422
    assert client.get("/centres/?limit=1000").status_code == 422


def test_missing_centre(client):
    assert client.get("/centres/12345").status_code == 404
