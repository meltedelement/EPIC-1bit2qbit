import sys
import os

import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from batcher import make_leaf, hash_pair, build_tree, get_root, MAX_LEAVES, push


class TestMakeLeaf:
    def test_deterministic(self):
        assert make_leaf("hello") == make_leaf("hello")

    def test_output_is_32_bytes(self):
        assert len(make_leaf("hello")) == 32

    def test_different_inputs_differ(self):
        assert make_leaf("hello") != make_leaf("world")

    def test_double_hash_differs_from_single(self):
        from web3 import Web3
        single = Web3.solidity_keccak(['bytes'], ["hello".encode('utf-8')])
        assert make_leaf("hello") != single

    def test_empty_string(self):
        assert len(make_leaf("")) == 32


class TestHashPair:
    def test_commutative(self):
        a, b = make_leaf("a"), make_leaf("b")
        assert hash_pair(a, b) == hash_pair(b, a)

    def test_output_is_32_bytes(self):
        assert len(hash_pair(make_leaf("a"), make_leaf("b"))) == 32

    def test_equal_inputs_valid(self):
        a = make_leaf("a")
        assert len(hash_pair(a, a)) == 32

    def test_different_pairs_differ(self):
        a, b, c = make_leaf("a"), make_leaf("b"), make_leaf("c")
        assert hash_pair(a, b) != hash_pair(a, c)


class TestBuildTree:
    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_tree([])

    def test_single_leaf_root_is_leaf(self):
        leaf = make_leaf("only")
        assert get_root(build_tree([leaf])) == leaf

    def test_two_leaves_root_equals_hash_pair(self):
        a, b = make_leaf("a"), make_leaf("b")
        assert get_root(build_tree([a, b])) == hash_pair(a, b)

    def test_deterministic_regardless_of_input_order(self):
        leaves = [make_leaf(m) for m in ["hello", "world", "foo", "bar"]]
        root1 = get_root(build_tree(leaves))
        root2 = get_root(build_tree(list(reversed(leaves))))
        assert root1 == root2

    def test_odd_leaf_count(self):
        leaves = [make_leaf("a"), make_leaf("b"), make_leaf("c")]
        sorted_l = sorted(leaves)
        expected_level1 = [
            hash_pair(sorted_l[0], sorted_l[1]),
            hash_pair(sorted_l[2], sorted_l[2]),
        ]
        expected_root = hash_pair(expected_level1[0], expected_level1[1])
        assert get_root(build_tree(leaves)) == expected_root

    def test_leaf_layer_is_globally_sorted(self):
        import random
        leaves = [make_leaf(str(i)) for i in range(6)]
        random.shuffle(leaves)
        tree = build_tree(leaves)
        assert tree[0] == sorted(leaves)

    def test_power_of_two_tree_depth(self):
        leaves = [make_leaf(str(i)) for i in range(8)]
        assert len(build_tree(leaves)) == 4


class TestGetRoot:
    def test_returns_first_element_of_last_layer(self):
        leaf = make_leaf("x")
        assert get_root([[leaf]]) == leaf

    def test_consistent_with_build_tree(self):
        leaves = [make_leaf(m) for m in ["a", "b", "c", "d"]]
        tree = build_tree(leaves)
        assert get_root(tree) == tree[-1][0]


class TestPush:
    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            push([])

    def test_single_chunk_calls_submit_once(self):
        fake = {"tx_hash": "0xabc", "root": "0xdef", "batch_index": 0, "leaf_count": 2}
        with patch("batcher.submit_batch", return_value=fake) as mock_submit:
            result = push(["hello", "world"])
            mock_submit.assert_called_once_with(["hello", "world"])
            assert len(result) == 1

    def test_oversized_list_splits_into_two_chunks(self):
        messages = [str(i) for i in range(MAX_LEAVES + 1)]
        fake = {"tx_hash": "0xabc", "root": "0xdef", "batch_index": 0, "leaf_count": 1}
        with patch("batcher.submit_batch", return_value=fake) as mock_submit:
            result = push(messages)
            assert mock_submit.call_count == 2
            assert len(mock_submit.call_args_list[0][0][0]) == MAX_LEAVES
            assert len(mock_submit.call_args_list[1][0][0]) == 1
            assert len(result) == 2
