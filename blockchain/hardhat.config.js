import '@nomicfoundation/hardhat-toolbox';
import 'dotenv/config';

const sepoliaConfig = process.env.SEPOLIA_RPC_URL && process.env.PRIVATE_KEY
  ? { sepolia: { url: process.env.SEPOLIA_RPC_URL, accounts: [process.env.PRIVATE_KEY] } }
  : {};

export default {
  solidity: '0.8.20',
  networks: {
    ...sepoliaConfig
  },
  etherscan: {
    apiKey: process.env.ETHERSCAN_API_KEY
  }
};
