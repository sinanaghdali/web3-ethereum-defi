"""Forge toolchain integration.

- Compile and deploy smart contracts using Forge

- Verify smart contracts on Etherscan
"""
import io
import logging

from pathlib import Path
from shutil import which
from subprocess import DEVNULL, PIPE

import psutil
from eth_typing import ChecksumAddress, HexAddress, HexStr
from web3 import Web3
from web3.contract import Contract

from eth_defi.abi import get_deployed_contract
from eth_defi.deploy import register_contract

logger = logging.getLogger(__name__)


#: Crash unless forge completes in 3 minutes
#:
DEFAULT_TIMEOUT = 3*60


class ForgeFailed(Exception):
    """Forge command failed."""


def _exec_cmd(
    cmd_line: list[str],
    censored_command: str,
    timeout=DEFAULT_TIMEOUT,
) -> str:
    """Execute the command line.

    :param timeout:
        Timeout in seconds

    :return:
        Deployed contract address
    """

    for x in cmd_line:
        assert type(x) == str, f"Got non-string in command line: {x} in {cmd_line}"

    # out = DEVNULL if sys.platform == "win32" else PIPE
    out = PIPE  # TODO: Are we set on a failure on Windows
    proc = psutil.Popen(cmd_line, stdin=DEVNULL, stdout=out, stderr=out)
    result = proc.wait(timeout)

    if result != 0:
        raise ForgeFailed(f"forge return code {result} when running: {censored_command}")

    for line in io.TextIOWrapper(proc.stdout, encoding="utf-8"):
        # Deployed to: 0x604Da6680Cb97A87403600B9AafBE60eeda97CA4
        if line.startswith("Deployed to: "):
            return line.split(":")[1].strip()

    raise ForgeFailed(f"Could not parse forge output: %s", proc.stdout.encode("utf-8"))


def deploy_contract_with_forge(
    web3: Web3,
    project_folder: Path,
    contract_file: Path,
    contract_name: str,
    private_key: str,
    constructor_args: list[str],
    etherscan_api_key: str | None = None,
    register_for_tracing=True,
    timeout=DEFAULT_TIMEOUT,
) -> Contract:
    """Deploys a new contract using Forge command from Foundry.

    - Uses Forge to verify the contract on Etherscan

    - For normal use :py:func:`deploy_contract` is much easier

    Example:

    .. code-block:: python

        token = deploy_contract(web3, deployer, "ERC20Mock.json", name, symbol, supply)
        print(f"Deployed ERC-20 token at {token.address}")

    :param web3:
        Web3 instance

    :param project_folder:
        Foundry

    :param contract_file:
        Contract path relative to the project folder.

        E.g. `src/TermsOfService.sol`.

    :param contract_name:
        The smart contract name within the file.

        E.g. `TermsOfServce`.

    :param constructor_args:
        Other arguments to pass to the contract's constructor.

        Need to be able to stringify these for forge.

    :param register_for_tracing:
        Make the symbolic contract information available on web3 instance.

        See :py:func:`get_contract_registry`

    :raise ContractDeploymentFailed:
        In the case we could not deploy the contract.

    :return:
        Contract proxy instance
    """
    assert isinstance(project_folder, Path)
    assert isinstance(contract_file, Path)
    assert type(contract_name) == str
    assert private_key.startswith("0x")

    json_rpc_url = web3.provider.endpoint_uri

    forge = which("forge")
    assert forge is not None, "No forge command in path, needed for the contract deployment"

    cmd_line = [
        forge,
        "create"
        "--rpc-url", json_rpc_url,
    ]

    if etherscan_api_key:
        cmd_line += [
            "--etherscan-api-key", etherscan_api_key
            "--verify"
        ]

    cmd_line += [
        f"{contract_file}:{contract_name}"
    ]

    censored_command = " ".join(cmd_line)

    logger.info(
        "Deploying a contract with forge. Working directory %s, forge command: %s",
        censored_command,
    )

    # Inject private key after logging
    cmd_line = [
        forge,
        "create"
        "--private-key", private_key,
    ] + cmd_line[2:]

    with project_folder:  # https://stackoverflow.com/a/14019583/315168
        assert (project_folder / "foundry.toml").exists(), f"foundry.toml missing: {project_folder}"
        assert contract_file.suffix == ".sol", f"Not Solidity source file: {contract_file}"
        assert contract_file.exists()

        contract_address = _exec_cmd(cmd_line, timeout=timeout, censored_command=censored_command)
        contract_abi = project_folder / "out" / contract_file / f"{contract_name}.abi"

        assert contract_abi.exists(), f"Forge did not produce ABI file: {contract_abi}"

    # Mad Web3.py API
    contract_address = ChecksumAddress(HexAddress(HexStr(contract_address)))
    instance = get_deployed_contract(
        web3,
        contract_abi,
        contract_address
    )

    if register_for_tracing:
        instance.name = contract_name
        register_contract(web3, contract_address, instance)

    return instance