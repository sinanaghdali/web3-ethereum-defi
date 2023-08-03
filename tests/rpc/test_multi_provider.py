"""MultiProviderWeb3 configuration tests."""

import pytest
from web3 import HTTPProvider, Web3

from eth_defi.hotwallet import HotWallet
from eth_defi.provider.anvil import AnvilLaunch, launch_anvil
from eth_defi.provider.multi_provider import create_multi_provider_web3, MultiProviderConfigurationError
from eth_defi.provider.named import get_provider_name
from eth_defi.trace import assert_transaction_success_with_explanation
from eth_defi.uniswap_v2.utils import ZERO_ADDRESS


@pytest.fixture(scope="module")
def anvil() -> AnvilLaunch:
    """Launch Anvil for the test backend."""
    anvil = launch_anvil(port=20002)
    try:
        yield anvil
    finally:
        anvil.close()


def test_multi_provider_mev_and_fallback():
    """Configure complex Web3 instance correctly."""
    config = """ 
    mev+https://rpc.mevblocker.io
    https://polygon-rpc.com
    https://bsc-dataseed2.bnbchain.org
    """
    web3 = create_multi_provider_web3(config)
    assert get_provider_name(web3.get_fallback_provider()) == "polygon-rpc.com"
    assert len(web3.get_fallback_provider().providers) == 2
    assert get_provider_name(web3.get_active_transact_provider()) == "rpc.mevblocker.io"
    assert web3.eth.block_number > 0

    mev_blocker = web3.get_configured_transact_provider()
    assert mev_blocker.provider_counter == {"call": 2, "transact": 0}


def test_multi_provider_fallback_only():
    config = """ 
    https://polygon-rpc.com
    """
    web3 = create_multi_provider_web3(config)
    assert get_provider_name(web3.get_fallback_provider()) == "polygon-rpc.com"


def test_multi_provider_empty_config():
    """Cannot start with empty config."""
    config = """
    """
    with pytest.raises(MultiProviderConfigurationError):
        create_multi_provider_web3(config)


def test_multi_provider_bad_url():
    """Cannot start with bad urls config."""
    config = """
    mev+https:/rpc.mevblocker.io
    polygon-rpc.com    
    """
    with pytest.raises(MultiProviderConfigurationError):
        create_multi_provider_web3(config)


def test_multi_provider_transact(anvil):
    """See we use MEV Blocker for doing transactions."""

    # Use Anvil as MEV blocker instance
    config = f""" 
    mev+{anvil.json_rpc_url}
    https://polygon-rpc.com
    """

    web3 = create_multi_provider_web3(config)

    # Need to connect to Anvil directly
    anvil_web3 = Web3(HTTPProvider(anvil.json_rpc_url))
    wallet = HotWallet.create_for_testing(anvil_web3)

    signed_tx = wallet.sign_transaction_with_new_nonce(
        {
            "from": wallet.address,
            "to": ZERO_ADDRESS,
            "value": 1,
            "gas": 100_000,
            "gasPrice": web3.eth.gas_price,
        }
    )

    tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    assert_transaction_success_with_explanation(anvil_web3, tx_hash)

    mev_blocker = web3.get_configured_transact_provider()
    assert mev_blocker.provider_counter == {"call": 2, "transact": 1}
