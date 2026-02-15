from app.core.metrics import (
    CACHE_HIT_TOTAL,
    CACHE_KEY_COUNT,
    CACHE_KEYS_SET_TOTAL,
    CACHE_MISS_TOTAL,
    CACHE_SET_TOTAL,
    record_cache_hit,
    record_cache_key_count,
    record_cache_miss,
    record_cache_set,
)


def _counter_value(counter, **labels):
    return counter.labels(**labels)._value.get()


def test_cache_metrics_record_hits_misses_and_sets():
    cache_label = "unit-cache"
    hit_before = _counter_value(CACHE_HIT_TOTAL, cache=cache_label)
    miss_before = _counter_value(CACHE_MISS_TOTAL, cache=cache_label)
    set_before = _counter_value(CACHE_SET_TOTAL, cache=cache_label)
    keys_set_before = _counter_value(CACHE_KEYS_SET_TOTAL, cache=cache_label)

    record_cache_hit(cache_label)
    record_cache_miss(cache_label)
    record_cache_set(cache_label, payload_bytes=256)

    assert _counter_value(CACHE_HIT_TOTAL, cache=cache_label) == hit_before + 1
    assert _counter_value(CACHE_MISS_TOTAL, cache=cache_label) == miss_before + 1
    assert _counter_value(CACHE_SET_TOTAL, cache=cache_label) == set_before + 1
    assert _counter_value(CACHE_KEYS_SET_TOTAL, cache=cache_label) == keys_set_before + 1


def test_cache_key_count_gauge_tracks_backend_key_count():
    backend_label = "memory-test"
    record_cache_key_count(backend_label, 0)
    before = CACHE_KEY_COUNT.labels(backend=backend_label)._value.get()
    record_cache_key_count(backend_label, 7)
    after = CACHE_KEY_COUNT.labels(backend=backend_label)._value.get()
    assert before == 0
    assert after == 7
