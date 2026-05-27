// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title MessageIntegrity
/// @notice Records Merkle batch roots and individual leaf hashes on-chain to provide
///         tamper-evident message integrity verification.
/// @dev Append-only: once a batch is recorded its root and timestamp are permanent.
///      Leaves are not stored in contract storage — they are emitted as events and
///      queryable via eth_getLogs. This keeps per-leaf cost at event-emission rates
///      (~375 gas/topic) rather than SSTORE rates (~20,000 gas/slot).
///      No reentrancy guard is applied: the contract never sends ETH, never calls
///      external addresses, and onlyOwner prevents untrusted callers entirely.
contract MessageIntegrity {

    /// @notice Caller is not the contract owner.
    error NotAuthorised();
    /// @notice Submitted leaf array is empty.
    error EmptyBatch();
    /// @notice Submitted leaf array exceeds the per-batch maximum of MAX_LEAVES.
    error BatchTooLarge();
    /// @notice Submitted Merkle root is the zero hash.
    error InvalidMerkleRoot();
    /// @notice Requested batch index is out of range.
    error BatchDoesNotExist();
    /// @notice Proposed new owner is the zero address.
    error InvalidAddress();

    /// @notice A single recorded batch containing a Merkle root and its commit timestamp.
    struct Batch {
        bytes32 merkleRoot;
        uint256 timestamp;
    }

    /// @notice Hard cap on leaves per batch. The Sepolia block gas limit is 60 M gas; at
    ///         ~2 000 gas per leaf (LeafRecorded event emission + calldata) and ~70 000 gas
    ///         fixed overhead, the theoretical maximum is ~29 965 leaves per transaction.
    ///         25 000 is set as the contract limit to provide headroom for gas price
    ///         fluctuation and transaction estimator variance.
    uint256 public constant MAX_LEAVES = 25_000;

    /// @notice Append-only array of all recorded batches.
    /// @dev The array index is permanent and used as the join key for LeafRecorded events.
    Batch[] public batches;

    /// @notice The wallet address permitted to record batches; set once at deployment.
    address public owner;

    /// @notice Emitted when contract ownership is transferred to a new wallet.
    /// @param previousOwner The wallet that held ownership before the transfer.
    /// @param newOwner The wallet that now holds ownership.
    event OwnershipTransferred(
        address indexed previousOwner,
        address indexed newOwner
    );

    /// @notice Emitted once per batch when a new Merkle root is committed to storage.
    /// @param batchIndex Position of this batch in the batches array; permanent, never reused.
    /// @param merkleRoot The keccak256 Merkle root computed from all leaves in this batch.
    /// @param timestamp Block timestamp at the moment of recording (Unix seconds).
    event BatchRecorded(
        uint256 indexed batchIndex,
        bytes32 indexed merkleRoot,
        uint256 timestamp
    );

    /// @notice Emitted once per leaf within a batch; the sole on-chain record of individual leaf hashes.
    /// @dev Indexing rationale (Solidity caps indexed fields at 3 per event):
    ///      - batchIndex indexed: verifier fetches all leaves for a known batch via eth_getLogs filter.
    ///      - leafHash indexed: verifier locates which batch contains a given hash via eth_getLogs filter.
    ///      - leafIndex NOT indexed: used only for ordering after retrieval, never as a filter key.
    /// @param batchIndex The batch this leaf belongs to; matches the corresponding BatchRecorded event.
    /// @param leafIndex Zero-based position of this leaf within the batch; used to reconstruct ordering.
    /// @param leafHash The double-keccak256 hash of the original message content.
    event LeafRecorded(
        uint256 indexed batchIndex,
        uint256 leafIndex,
        bytes32 indexed leafHash
    );

    /// @notice Sets the deploying wallet as the sole authorised recorder.
    constructor() {
        owner = msg.sender;
    }

    /// @notice Reverts with NotAuthorised if the caller is not the owner.
    modifier onlyOwner() {
        if (msg.sender != owner) revert NotAuthorised();
        _;
    }

    /// @notice Records a new Merkle batch: persists the root and timestamp in storage,
    ///         then emits all leaf hashes as events.
    /// @dev Gas notes:
    ///      - `leaves` is `calldata` to avoid copying the array into memory before iteration.
    ///      - `idx` caches `batches.length` before the push so the storage slot is read once,
    ///        not once per loop iteration.
    ///      - Leaf hashes are emitted rather than stored to use event-emission gas rates.
    ///      Follows Checks-Effects-Interactions: modifier check → state mutation → events.
    /// @param merkleRoot The keccak256 Merkle root of the provided leaves.
    /// @param leaves Array of individual leaf hashes (double-keccak256 of each message).
    /// @dev The contract does not verify that merkleRoot is consistent with leaves.
    ///      Recomputing the tree on-chain would cost O(n log n) keccak256 operations at EVM
    ///      gas rates, making large batches prohibitively expensive. Trust is instead enforced
    ///      by the onlyOwner guard — only the deployer wallet can submit data.
    function recordBatch(
        bytes32 merkleRoot,
        bytes32[] calldata leaves
    ) external onlyOwner {
        if (leaves.length == 0) revert EmptyBatch();
        if (leaves.length > MAX_LEAVES) revert BatchTooLarge();
        if (merkleRoot == bytes32(0)) revert InvalidMerkleRoot();

        uint256 idx = batches.length;
        batches.push(Batch(merkleRoot, block.timestamp));

        emit BatchRecorded(idx, merkleRoot, block.timestamp);

        for (uint256 i = 0; i < leaves.length; i++) {
            emit LeafRecorded(idx, i, leaves[i]);
        }
    }

    /// @notice Transfers ownership to a new wallet address.
    /// @dev Single-step transfer: takes effect immediately on call. Caller is responsible
    ///      for ensuring newOwner is a valid, accessible address. Specifically choosing not
    ///      to implement the newer Ownable2Step, as it is out of scope for this project.
    /// @param newOwner The address to transfer ownership to; must not be the zero address.
    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidAddress(); 
        owner = newOwner;
        emit OwnershipTransferred(owner, newOwner);
    }

    /// @notice Returns the Merkle root and timestamp for a recorded batch.
    /// @param index The batch index to query.
    /// @return merkleRoot The Merkle root stored for this batch.
    /// @return timestamp The block timestamp when this batch was recorded (Unix seconds).
    function getBatch(uint256 index)
        external
        view
        returns (bytes32 merkleRoot, uint256 timestamp)
    {
        if (index >= batches.length) revert BatchDoesNotExist();
        Batch storage b = batches[index];
        return (b.merkleRoot, b.timestamp);
    }

    /// @notice Returns the total number of batches recorded so far.
    /// @return The length of the batches array.
    function getBatchCount() external view returns (uint256) {
        return batches.length;
    }
}
