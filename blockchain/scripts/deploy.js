import pkg from 'hardhat';
const { ethers } = pkg;

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log('Deploying from:', deployer.address);

  const MessageIntegrity = await ethers.getContractFactory('MessageIntegrity');
  const contract = await MessageIntegrity.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();

  // Retrieve the mined receipt to get actual gas figures rather than estimates
  const tx = contract.deploymentTransaction();
  const receipt = await tx.wait();

  const gasCostWei = receipt.gasUsed * receipt.gasPrice;

  console.log('\nDeployment successful');
  console.log('  Contract address :', address);
  console.log('  Transaction hash :', receipt.hash);
  console.log('  Deployment cost  :', ethers.formatEther(gasCostWei), 'ETH');
  console.log('\nEtherscan');
  console.log('  Transaction :', `https://sepolia.etherscan.io/tx/${receipt.hash}`);
  console.log('  Contract    :', `https://sepolia.etherscan.io/address/${address}`);
  console.log('\nAdd to your .env files:');
  console.log(`  CONTRACT_ADDRESS=${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
