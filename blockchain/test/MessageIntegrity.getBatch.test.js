import { expect } from 'chai';
import { loadFixture } from '@nomicfoundation/hardhat-network-helpers';
import { deployFixture, sampleLeaves, sampleRoot } from './helpers/fixtures.js';

describe('MessageIntegrity — getBatch', function () {

  describe('happy path', function () {

    it('returns the correct root and timestamp for a recorded batch', async function () {
      const { contract } = await loadFixture(deployFixture);
      await contract.recordBatch(sampleRoot, sampleLeaves);
      const [storedRoot, storedTimestamp] = await contract.getBatch(0);
      expect(storedRoot).to.equal(sampleRoot);
      expect(storedTimestamp).to.be.gt(0);
    });

  });

  describe('revert guards', function () {

    it('reverts BatchDoesNotExist when no batches have been recorded', async function () {
      const { contract } = await loadFixture(deployFixture);
      await expect(
        contract.getBatch(0)
      ).to.be.revertedWithCustomError(contract, 'BatchDoesNotExist');
    });

    it('reverts BatchDoesNotExist for an index beyond the last recorded batch', async function () {
      const { contract } = await loadFixture(deployFixture);
      await contract.recordBatch(sampleRoot, sampleLeaves);
      await expect(
        contract.getBatch(1)
      ).to.be.revertedWithCustomError(contract, 'BatchDoesNotExist');
    });

  });

});
