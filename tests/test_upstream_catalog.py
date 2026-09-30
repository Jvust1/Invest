from invest.upstream_catalog import catalog_summary, list_catalog


def test_high_star_batch_contains_exactly_fifty_projects():
    projects = list_catalog()
    assert len(projects) == 50
    assert len({project["repo"] for project in projects}) == 50
    assert all(project["stars"] > 1000 for project in projects)


def test_high_star_batch_has_license_and_capability_boundaries():
    projects = list_catalog()
    assert all(project["license"] for project in projects)
    assert all(project["capabilities"] for project in projects)
    assert {"MIT", "Apache-2.0"} <= {project["license"] for project in projects}
    assert catalog_summary()["capability_count"] >= 15
