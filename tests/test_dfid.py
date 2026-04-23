"""Tests for DecisionFlow ID helpers."""

import uuid

from dir_core.dfid import new_dfid, new_dfid_with_parent


def test_new_dfid_is_uuid_v4_string() -> None:
    d = new_dfid()
    uuid.UUID(d, version=4)


def test_new_dfid_unique() -> None:
    ids = {new_dfid() for _ in range(50)}
    assert len(ids) == 50


def test_new_dfid_with_parent_is_uuid_and_distinct() -> None:
    parent = new_dfid()
    child = new_dfid_with_parent(parent)
    uuid.UUID(child, version=4)
    assert child != parent
