import { ethers } from 'ethers';
import ABI from './abi.json';

const DEPLOY_BLOCK = 10_939_625;

export interface VerificationResult {
  isValid: boolean;
  reason: string;
  leafHash?: string;
  batchIndex?: number;
  merkleRoot?: string;
  timestamp?: Date;
  txHash?: string;
}

function makeLeaf(message: string): string {
  const first = ethers.keccak256(ethers.toUtf8Bytes(message));
  const second = ethers.keccak256(ethers.getBytes(first));
  return second;
}

function hashPair(a: string, b: string): string {
  const [left, right] = [a, b].sort();
  return ethers.keccak256(ethers.concat([ethers.getBytes(left), ethers.getBytes(right)]));
}

function buildTree(leaves: string[]): string[][] {
  let layer = [...leaves].sort();
  const tree: string[][] = [layer];

  while (layer.length > 1) {
    if (layer.length % 2 === 1) {
      layer = [...layer, layer[layer.length - 1]];
    }
    const next: string[] = [];
    for (let i = 0; i < layer.length; i += 2) {
      next.push(hashPair(layer[i], layer[i + 1]));
    }
    layer = next;
    tree.push(layer);
  }

  return tree;
}

function getProof(tree: string[][], leaf: string): string[] {
  const proof: string[] = [];
  let index = tree[0].indexOf(leaf);

  if (index === -1) {
    throw new Error(`Leaf not found in tree: ${leaf}`);
  }

  for (let i = 0; i < tree.length - 1; i++) {
    const layer = tree[i];
    const siblingIndex = index % 2 === 0 ? index + 1 : index - 1;
    proof.push(siblingIndex < layer.length ? layer[siblingIndex] : layer[index]);
    index = Math.floor(index / 2);
  }

  return proof;
}

function verifyProof(proof: string[], leaf: string, root: string): boolean {
  let computed = leaf;
  for (const sibling of proof) {
    computed = hashPair(computed, sibling);
  }
  return computed === root;
}

export async function verifyMessage(message: string): Promise<VerificationResult> {
  try {
    const CONTRACT_ADDRESS = import.meta.env.VITE_CONTRACT_ADDRESS as string;
    const SEPOLIA_RPC_URL = import.meta.env.VITE_SEPOLIA_RPC_URL as string;

    const missingVars = [
      !CONTRACT_ADDRESS && 'VITE_CONTRACT_ADDRESS',
      !SEPOLIA_RPC_URL && 'VITE_SEPOLIA_RPC_URL',
    ].filter(Boolean);
    if (missingVars.length > 0) {
      throw new Error(`Missing required environment variable(s): ${missingVars.join(', ')}`);
    }

    const provider = new ethers.JsonRpcProvider(SEPOLIA_RPC_URL);
    const contract = new ethers.Contract(CONTRACT_ADDRESS, ABI.abi, provider);

    const leafHash = makeLeaf(message);

    const leafEvents = await contract.queryFilter(
      contract.filters.LeafRecorded(null, null, leafHash),
      DEPLOY_BLOCK,
      'latest'
    );

    if (leafEvents.length === 0) {
      return { isValid: false, reason: 'Message not found on chain', leafHash };
    }

    const leafEvent = leafEvents[0] as ethers.EventLog;
    const batchIndex = Number(leafEvent.args.batchIndex);
    const txHash = leafEvent.transactionHash;

    const [merkleRoot, timestamp] = await contract.getBatch(batchIndex);

    const leavesInBatch = await contract.queryFilter(
      contract.filters.LeafRecorded(batchIndex, null, null),
      DEPLOY_BLOCK,
      'latest'
    );

    const allLeaves = leavesInBatch.map(e => (e as ethers.EventLog).args.leafHash as string);
    const tree = buildTree(allLeaves);
    const rebuiltRoot = tree[tree.length - 1][0];

    if (rebuiltRoot !== merkleRoot) {
      return { isValid: false, reason: 'Root mismatch — batch data is inconsistent', leafHash, batchIndex, txHash };
    }

    const proof = getProof(tree, leafHash);
    const isValid = verifyProof(proof, leafHash, rebuiltRoot);

    return {
      isValid,
      reason: isValid ? 'Proof verified' : 'Proof invalid',
      leafHash,
      batchIndex,
      merkleRoot: merkleRoot as string,
      timestamp: new Date(Number(timestamp) * 1000),
      txHash,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Please try again later';
    return { isValid: false, reason: `Verification failed: ${message}` };
  }
}
