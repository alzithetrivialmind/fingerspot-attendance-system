def test_create_and_list_departments(client):
    # Test creating a department
    response = client.post("/master-data/departments", json={"name": "Engineering"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Engineering"
    assert "id" in data
    
    # Test listing departments
    response = client.get("/master-data/departments")
    assert response.status_code == 200
    data_list = response.json()
    assert len(data_list) == 1
    assert data_list[0]["name"] == "Engineering"

def test_create_and_list_positions(client):
    # Test creating a position
    response = client.post("/master-data/positions", json={"name": "Software Developer"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Software Developer"
    
    # Test listing positions
    response = client.get("/master-data/positions")
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_create_and_list_companies(client):
    # Test creating a company
    response = client.post("/master-data/companies", json={"name": "Tech Corp"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Tech Corp"
    
    # Test listing companies
    response = client.get("/master-data/companies")
    assert response.status_code == 200
    assert len(response.json()) == 1
