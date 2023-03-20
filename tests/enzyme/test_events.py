"""Read Enzyme vault events.

"""
from eth_typing import HexAddress
from web3 import Web3
from web3.contract import Contract

from eth_defi.enzyme.deployment import EnzymeDeployment, RateAsset
from eth_defi.uniswap_v2.deployment import UniswapV2Deployment


def test_read_deposit(
        web3: Web3,
        deployer: HexAddress,
        user_1: HexAddress,
        user_2,
        user_3,
        weth: Contract,
        mln: Contract,
        usdc: Contract,
        weth_usd_mock_chainlink_aggregator: Contract,
        usdc_usd_mock_chainlink_aggregator: Contract,
        dual_token_deployment: EnzymeDeployment,
        uniswap_v2: UniswapV2Deployment,
        weth_usdc_pair: Contract,
):
    """Deploy Enzyme protocol, single USDC nominated vault and buy in."""

    deployment = EnzymeDeployment.deploy_core(
        web3,
        deployer,
        mln,
        weth,
    )

    # Create a vault for user 1
    # where we nominate everything in USDC
    deployment.add_primitive(
        usdc,
        usdc_usd_mock_chainlink_aggregator,
        RateAsset.USD,
    )

    comptroller, vault = deployment.create_new_vault(
        user_1,
        usdc,
    )

    assert comptroller.functions.getDenominationAsset().call() == usdc.address
    assert vault.functions.getTrackedAssets().call() == [usdc.address]

    # User 2 buys into the vault
    # See Shares.sol
    #
    # Buy shares for 500 USDC, receive min share
    usdc.functions.transfer(user_1, 500 * 10 ** 6).transact({"from": deployer})
    usdc.functions.approve(comptroller.address, 500*10**6).transact({"from": user_1})
    comptroller.functions.buyShares(500*10**6, 1).transact({"from": user_1})

    # See user 2 received shares
    balance = vault.functions.balanceOf(user_1).call()
    assert balance == 500*10**6
