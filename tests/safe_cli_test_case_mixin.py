import os
from typing import List, Optional

from eth_account import Account

from gnosis.eth import EthereumClient
from gnosis.eth.contracts import get_safe_contract
from gnosis.safe import ProxyFactory, Safe
from gnosis.safe.safe_create2_tx import SafeCreate2Tx
from gnosis.safe.tests.utils import generate_salt_nonce

from safe_cli.safe_operator import SafeOperator


class SafeCliTestCaseMixin:
    ETHEREUM_NODE_URL: str = os.environ.get('ETHEREUM_NODE_URL', 'http://localhost:8545')
    ETHEREUM_ACCOUNT_KEY: str = '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'  # Hardhat #0

    @classmethod
    def setUpClass(cls) -> None:
        cls.ethereum_node_url = cls.ETHEREUM_NODE_URL
        cls.ethereum_client = EthereumClient(cls.ethereum_node_url)
        cls.w3 = cls.ethereum_client.w3
        cls.ethereum_test_account = Account.from_key(cls.ETHEREUM_ACCOUNT_KEY)
        cls.safe_contract_address = Safe.deploy_master_contract(cls.ethereum_client,
                                                                cls.ethereum_test_account).contract_address
        cls.safe_old_contract_address = Safe.deploy_master_contract_v1_0_0(cls.ethereum_client,
                                                                           cls.ethereum_test_account).contract_address
        cls.proxy_factory = ProxyFactory(
            ProxyFactory.deploy_proxy_factory_contract(cls.ethereum_client,
                                                       cls.ethereum_test_account).contract_address,
            cls.ethereum_client)

    def build_test_safe(self, number_owners: int = 3, threshold: Optional[int] = None,
                        owners: Optional[List[str]] = None, fallback_handler: Optional[str] = None) -> SafeCreate2Tx:
        salt_nonce = generate_salt_nonce()
        owners = owners if owners else [Account.create().address for _ in range(number_owners)]
        threshold = threshold if threshold else len(owners) - 1

        gas_price = self.ethereum_client.w3.eth.gasPrice
        return Safe.build_safe_create2_tx(self.ethereum_client, self.safe_contract_address,
                                          self.proxy_factory.address, salt_nonce, owners, threshold,
                                          fallback_handler=fallback_handler,
                                          gas_price=gas_price, payment_token=None, fixed_creation_cost=0)

    def deploy_test_safe(self, number_owners: int = 3, threshold: Optional[int] = None,
                         owners: Optional[List[str]] = None, initial_funding_wei: int = 0,
                         fallback_handler: Optional[str] = None) -> SafeCreate2Tx:
        owners = owners if owners else [Account.create().address for _ in range(number_owners)]
        if not threshold:
            threshold = len(owners) - 1 if len(owners) > 1 else 1
        safe_creation_tx = self.build_test_safe(threshold=threshold, owners=owners, fallback_handler=fallback_handler)
        funder_account = self.ethereum_test_account

        ethereum_tx_sent = self.proxy_factory.deploy_proxy_contract_with_nonce(funder_account,
                                                                               self.safe_contract_address,
                                                                               safe_creation_tx.safe_setup_data,
                                                                               safe_creation_tx.salt_nonce)

        safe_address = ethereum_tx_sent.contract_address
        if initial_funding_wei:
            self.send_ether(safe_address, initial_funding_wei)

        safe_instance = get_safe_contract(self.w3, safe_address)

        self.assertEqual(safe_instance.functions.getThreshold().call(), threshold)
        self.assertEqual(safe_instance.functions.getOwners().call(), owners)
        self.assertEqual(safe_address, safe_creation_tx.safe_address)
        return safe_creation_tx

    def setup_operator(self, number_owners: int = 1) -> SafeOperator:
        assert number_owners >= 1, 'Number of owners cannot be less than 1!'
        safe_address = self.deploy_test_safe(owners=[self.ethereum_test_account.address]).safe_address
        safe_operator = SafeOperator(safe_address, self.ethereum_node_url)
        safe_operator.load_cli_owners([self.ethereum_test_account.key.hex()])
        for _ in range(number_owners - 1):
            account = Account.create()
            safe_operator.add_owner(account.address)
            safe_operator.load_cli_owners([account.key.hex()])
        return safe_operator

    def send_ether(self, to: str, value: int) -> bytes:
        return self.w3.eth.sendTransaction({'to': to, 'value': value, 'from': self.ethereum_test_account.address})
