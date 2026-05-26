import pkg from 'hardhat';
const { ethers } = pkg;

// ---------------------------------------------------------------------------
// Shared test data
// ---------------------------------------------------------------------------

export const leaf1 = ethers.keccak256(ethers.toUtf8Bytes('message one'));
export const leaf2 = ethers.keccak256(ethers.toUtf8Bytes('message two'));
export const leaf3 = ethers.keccak256(ethers.toUtf8Bytes('message three'));
export const sampleLeaves = [leaf1, leaf2, leaf3];

// Contract does not verify root consistency with leaves — any valid bytes32 works here
export const sampleRoot = ethers.keccak256(ethers.concat([leaf1, leaf2, leaf3]));

export const ZERO_BYTES32 = ethers.ZeroHash;
export const ZERO_ADDRESS = ethers.ZeroAddress;

// ---------------------------------------------------------------------------
// Deployment fixture
// Consumed via loadFixture() — Hardhat snapshots state after first run and
// restores it before each test, avoiding a full redeploy per test.
// ---------------------------------------------------------------------------

export async function deployFixture() {
  const [owner, nonOwner, thirdParty] = await ethers.getSigners();
  const MessageIntegrity = await ethers.getContractFactory('MessageIntegrity');
  const contract = await MessageIntegrity.deploy();
  await contract.waitForDeployment();
  return { contract, owner, nonOwner, thirdParty };
}
