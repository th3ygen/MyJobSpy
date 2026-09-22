def test_package_imports():
    from jobspy import scrape_jobs

    assert callable(scrape_jobs)


def test_rapidfuzz_available():
    from rapidfuzz import fuzz

    assert fuzz.token_sort_ratio("abc", "abc") == 100
