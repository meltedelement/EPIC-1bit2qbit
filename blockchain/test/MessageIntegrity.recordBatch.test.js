import { expect } from 'chai';
import pkg from 'hardhat';
const { ethers } = pkg;
import { loadFixture } from '@nomicfoundation/hardhat-network-helpers';
import { anyValue } from '@nomicfoundation/hardhat-chai-matchers/withArgs.js';
import { deployFixture, leaf1, leaf2, leaf3, sampleLeaves, sampleRoot, ZERO_BYTES32 } from './helpers/fixtures.js';

describe('MessageIntegrity — recordBatch', function () {

  describe('happy path', function () {

    it('increments the batch count', async function () {
      const { contract } = await loadFixture(deployFixture);
      await contract.recordBatch(sampleRoot, sampleLeaves);
      expect(await contract.getBatchCount()).to.equal(1);
    });

    it('stores the correct merkle root and a non-zero timestamp', async function () {
      const { contract } = await loadFixture(deployFixture);
      await contract.recordBatch(sampleRoot, sampleLeaves);
      const [storedRoot, storedTimestamp] = await contract.getBatch(0);
      expect(storedRoot).to.equal(sampleRoot);
      expect(storedTimestamp).to.be.gt(0);
    });

    it('emits BatchRecorded with correct batchIndex and merkleRoot', async function () {
      const { contract } = await loadFixture(deployFixture);
      await expect(contract.recordBatch(sampleRoot, sampleLeaves))
        .to.emit(contract, 'BatchRecorded')
        .withArgs(0, sampleRoot, anyValue);
    });

    it('emits a LeafRecorded event for every leaf in order', async function () {
      const { contract } = await loadFixture(deployFixture);
      const tx = contract.recordBatch(sampleRoot, sampleLeaves);
      await expect(tx).to.emit(contract, 'LeafRecorded').withArgs(0, 0, leaf1);
      await expect(tx).to.emit(contract, 'LeafRecorded').withArgs(0, 1, leaf2);
      await expect(tx).to.emit(contract, 'LeafRecorded').withArgs(0, 2, leaf3);
    });

    it('assigns sequential batchIndex values across multiple batches', async function () {
      const { contract } = await loadFixture(deployFixture);
      const root2 = ethers.keccak256(ethers.toUtf8Bytes('second root'));

      await expect(contract.recordBatch(sampleRoot, sampleLeaves))
        .to.emit(contract, 'BatchRecorded').withArgs(0, sampleRoot, anyValue);

      await expect(contract.recordBatch(root2, [leaf1]))
        .to.emit(contract, 'BatchRecorded').withArgs(1, root2, anyValue);

      expect(await contract.getBatchCount()).to.equal(2);
    });

  });

  describe('revert guards', function () {

    it('reverts NotAuthorised when called by a non-owner', async function () {
      const { contract, nonOwner } = await loadFixture(deployFixture);
      await expect(
        contract.connect(nonOwner).recordBatch(sampleRoot, sampleLeaves)
      ).to.be.revertedWithCustomError(contract, 'NotAuthorised');
    });

    it('reverts EmptyBatch when leaves array is empty', async function () {
      const { contract } = await loadFixture(deployFixture);
      await expect(
        contract.recordBatch(sampleRoot, [])
      ).to.be.revertedWithCustomError(contract, 'EmptyBatch');
    });

    it('reverts InvalidMerkleRoot when merkleRoot is the zero hash', async function () {
      const { contract } = await loadFixture(deployFixture);
      await expect(
        contract.recordBatch(ZERO_BYTES32, sampleLeaves)
      ).to.be.revertedWithCustomError(contract, 'InvalidMerkleRoot');
    });

    it('reverts BatchTooLarge when leaves array exceeds MAX_LEAVES', async function () {
      const { contract } = await loadFixture(deployFixture);
      const maxLeaves = Number(await contract.MAX_LEAVES());
      const tooManyLeaves = Array(maxLeaves + 1).fill(leaf1);
      await expect(
        contract.recordBatch(sampleRoot, tooManyLeaves)
      ).to.be.revertedWithCustomError(contract, 'BatchTooLarge');
    });

  });

});
