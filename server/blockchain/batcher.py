import json
import os

from dotenv import load_dotenv
from web3 import Web3

load_dotenv()


def _make_leaf(message: str) -> bytes:
    first = Web3.solidity_keccak(["bytes"], [message.encode("utf-8")])
    second = Web3.solidity_keccak(["bytes32"], [first])
    # Double-hash so leaves and internal nodes are produced by structurally
    # different operations, preventing an attacker from substituting an
    # internal node as a valid leaf (second-preimage resistance).
    return second


def _hash_pair(a: bytes, b: bytes) -> bytes:
    left, right = (a, b) if a <= b else (b, a)
    # Sort before hashing (sortPairs convention): the verifier never needs to
    # know which side a sibling sits on — it always sorts before hashing.
    return Web3.solidity_keccak(["bytes32", "bytes32"], [left, right])


def _build_tree(leaves: list[bytes]) -> list[list[bytes]]:
    if not leaves:
        raise ValueError("Cannot build Merkle tree from empty leaf list")

    layer = sorted(leaves)
    tree = [layer]

    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer = layer + [layer[-1]]
        layer = [_hash_pair(layer[i], layer[i + 1]) for i in range(0, len(layer), 2)]
        tree.append(layer)

    return tree


def _get_root(tree: list[list[bytes]]) -> bytes:
    return tree[-1][0]


MAX_LEAVES = 8_000


def _submit_batch(messages: list[str]) -> dict:
    if not messages:
        raise ValueError("Cannot submit empty batch")
    if len(messages) > MAX_LEAVES:
        raise ValueError(f"Batch exceeds MAX_LEAVES limit ({len(messages)} > {MAX_LEAVES})")

    rpc_url = os.getenv("SEPOLIA_RPC_URL")
    contract_address = os.getenv("CONTRACT_ADDRESS")
    private_key = os.getenv("PRIVATE_KEY")

    missing = [
        name
        for name, val in [
            ("SEPOLIA_RPC_URL", rpc_url),
            ("CONTRACT_ADDRESS", contract_address),
            ("PRIVATE_KEY", private_key),
        ]
        if val is None
    ]
    if missing:
        raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")

    w3 = Web3(Web3.HTTPProvider(rpc_url))

    with open(os.path.join(os.path.dirname(__file__), "abi.json"), encoding="utf-8") as f:
        contract_abi = json.load(f)["abi"]

    contract = w3.eth.contract(
        address=contract_address,
        abi=contract_abi,
    )

    account = w3.eth.account.from_key(private_key)
    leaves = [_make_leaf(m) for m in messages]
    tree = _build_tree(leaves)
    root = _get_root(tree)
    sorted_leaves = tree[0]

    tx = contract.functions.recordBatch(root, sorted_leaves).build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gasPrice": w3.eth.gas_price,
        }
    )

    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status != 1:
        raise ValueError(f"Transaction {tx_hash.hex()} reverted on-chain")

    events = contract.events.BatchRecorded().process_receipt(receipt)
    if not events:
        raise ValueError(f"BatchRecorded event not found in transaction {tx_hash.hex()}")

    batch_index = events[0]["args"]["batchIndex"]

    return {
        "tx_hash": tx_hash.hex(),
        "root": root.hex(),
        "batch_index": batch_index,
        "leaf_count": len(sorted_leaves),
    }


def add_to_blockchain(messages: list[str]) -> list[dict]:
    if not messages:
        raise ValueError("Cannot push empty message list")

    results = []
    for i in range(0, len(messages), MAX_LEAVES):
        results.append(_submit_batch(messages[i : i + MAX_LEAVES]))
    return results
