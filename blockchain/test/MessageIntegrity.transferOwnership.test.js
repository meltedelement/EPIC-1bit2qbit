import { expect } from 'chai';
import { loadFixture } from '@nomicfoundation/hardhat-network-helpers';
import { deployFixture, sampleLeaves, sampleRoot, ZERO_ADDRESS } from './helpers/fixtures.js';

describe('MessageIntegrity — transferOwnership', function () {

  describe('happy path', function () {

    it('updates the owner to the new address', async function () {
      const { contract, nonOwner } = await loadFixture(deployFixture);
      await contract.transferOwnership(nonOwner.address);
      expect(await contract.owner()).to.equal(nonOwner.address);
    });

    it('emits OwnershipTransferred with previous and new owner', async function () {
      const { contract, owner, nonOwner } = await loadFixture(deployFixture);
      await expect(contract.transferOwnership(nonOwner.address))
        .to.emit(contract, 'OwnershipTransferred')
        .withArgs(owner.address, nonOwner.address);
    });

    it('allows the new owner to record a batch after transfer', async function () {
      const { contract, nonOwner } = await loadFixture(deployFixture);
      await contract.transferOwnership(nonOwner.address);
      await expect(
        contract.connect(nonOwner).recordBatch(sampleRoot, sampleLeaves)
      ).to.emit(contract, 'BatchRecorded');
    });

    it('prevents the previous owner from recording a batch after transfer', async function () {
      const { contract, owner, nonOwner } = await loadFixture(deployFixture);
      await contract.transferOwnership(nonOwner.address);
      await expect(
        contract.connect(owner).recordBatch(sampleRoot, sampleLeaves)
      ).to.be.revertedWithCustomError(contract, 'NotAuthorised');
    });

  });

  describe('revert guards', function () {

    it('reverts NotAuthorised when called by a non-owner', async function () {
      const { contract, nonOwner, thirdParty } = await loadFixture(deployFixture);
      await expect(
        contract.connect(nonOwner).transferOwnership(thirdParty.address)
      ).to.be.revertedWithCustomError(contract, 'NotAuthorised');
    });

    it('reverts InvalidAddress when proposed new owner is the zero address', async function () {
      const { contract } = await loadFixture(deployFixture);
      await expect(
        contract.transferOwnership(ZERO_ADDRESS)
      ).to.be.revertedWithCustomError(contract, 'InvalidAddress');
    });

  });

});
