import { expect } from 'chai';
import { loadFixture } from '@nomicfoundation/hardhat-network-helpers';
import { deployFixture } from './helpers/fixtures.js';

describe('MessageIntegrity — Deployment', function () {

  it('sets the deployer as owner', async function () {
    const { contract, owner } = await loadFixture(deployFixture);
    expect(await contract.owner()).to.equal(owner.address);
  });

  it('starts with zero batches', async function () {
    const { contract } = await loadFixture(deployFixture);
    expect(await contract.getBatchCount()).to.equal(0);
  });

});
