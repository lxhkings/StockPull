def test_chunked_splits_into_fixed_size_batches():
    from batch_utils import chunked
    result = list(chunked([1, 2, 3, 4, 5], 2))
    assert result == [[1, 2], [3, 4], [5]]


def test_chunked_exact_multiple():
    from batch_utils import chunked
    result = list(chunked([1, 2, 3, 4], 2))
    assert result == [[1, 2], [3, 4]]


def test_chunked_empty_sequence():
    from batch_utils import chunked
    result = list(chunked([], 3))
    assert result == []


def test_chunked_size_larger_than_sequence():
    from batch_utils import chunked
    result = list(chunked([1, 2], 10))
    assert result == [[1, 2]]
