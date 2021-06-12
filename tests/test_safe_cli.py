import unittest

from eth_account import Account
from web3 import Web3

from gnosis.safe import Safe

from safe_cli.prompt_parser import PromptParser
from safe_cli.safe_operator import SafeOperator

from .safe_cli_test_case_mixin import SafeCliTestCaseMixin


class SafeCliTestCase(SafeCliTestCaseMixin, unittest.TestCase):
    def test_safe_cli_happy_path(self):
        accounts = [self.ethereum_test_account, Account.create()]
        account_addresses = [account.address for account in accounts]
        safe_address = self.deploy_test_safe(owners=account_addresses, threshold=2,
                                             initial_funding_wei=self.w3.toWei(1, 'ether')).safe_address
        safe = Safe(safe_address, self.ethereum_client)
        safe_operator = SafeOperator(safe_address, self.ethereum_node_url)
        prompt_parser = PromptParser(safe_operator)
        random_address = Account.create().address

        self.assertEqual(safe_operator.accounts, set())
        prompt_parser.process_command(f'load_cli_owners {self.ethereum_test_account.key.hex()}')
        self.assertEqual(safe_operator.default_sender, self.ethereum_test_account)
        self.assertEqual(safe_operator.accounts, {self.ethereum_test_account})

        prompt_parser.process_command(f'send_ether {random_address} 1')  # No enough signatures
        self.assertEqual(self.ethereum_client.get_balance(random_address), 0)

        value = 123
        prompt_parser.process_command(f'load_cli_owners {accounts[1].key.hex()}')
        prompt_parser.process_command(f'send_ether {random_address} {value}')
        self.assertEqual(self.ethereum_client.get_balance(random_address), value)

        # Change threshold
        self.assertEqual(safe_operator.safe_cli_info.threshold, 2)
        self.assertEqual(safe.retrieve_threshold(), 2)
        prompt_parser.process_command('change_threshold 1')
        self.assertEqual(safe_operator.safe_cli_info.threshold, 1)
        self.assertEqual(safe.retrieve_threshold(), 1)

        # Approve Hash
        safe_tx_hash = Web3.keccak(text='hola')
        self.assertFalse(safe_operator.safe.retrieve_is_hash_approved(accounts[0].address, safe_tx_hash))
        prompt_parser.process_command(f'approve_hash {safe_tx_hash.hex()} {accounts[0].address}')
        self.assertTrue(safe_operator.safe.retrieve_is_hash_approved(accounts[0].address, safe_tx_hash))

        # Remove owner
        self.assertEqual(len(safe_operator.safe_cli_info.owners), 2)
        self.assertEqual(len(safe.retrieve_owners()), 2)
        prompt_parser.process_command(f'remove_owner {accounts[1].address}')
        self.assertEqual(safe_operator.safe_cli_info.owners, [self.ethereum_test_account.address])
        self.assertEqual(safe.retrieve_owners(), [self.ethereum_test_account.address])

    def test_pre_change_shuttling(self):
        accounts = [self.ethereum_test_account, Account.create()]
        account_addresses = [account.address for account in accounts]

        safe_address = self.deploy_test_safe(owners=account_addresses, threshold=2,
                                             initial_funding_wei=self.w3.toWei(1, 'ether')).safe_address
        safe = Safe(safe_address, self.ethereum_client)

        operator_0 = SafeOperator(safe_address, self.ethereum_node_url)
        operator_0.load_cli_owners([accounts[0].key.hex()])
        self.assertEqual(operator_0.accounts, {self.ethereum_test_account})
        self.assertEqual(operator_0.default_sender, self.ethereum_test_account)

        operator_1 = SafeOperator(safe_address, self.ethereum_node_url)
        operator_1.load_cli_owners([accounts[1].key.hex()])
        self.assertEqual(operator_1.accounts, {accounts[1]})
        self.assertEqual(operator_1.default_sender, None)  # account 1 has no eth, so doesn't get added /shrug

        # Change threshold:

        self.assertEqual(operator_0.safe_cli_info.threshold, 2)
        self.assertEqual(safe.retrieve_threshold(), 2)

        data = operator_0.pre_change_threshold(1)
        self.assertEqual(data, '0x694e80c30000000000000000000000000000000000000000000000000000000000000001')

        sigs = operator_0.sign_multisig_tx(data)
        sigs_new = operator_1.sign_multisig_tx(data, sigs)

        operator_0.execute_signed(data, sigs_new)
        self.assertEqual(safe.retrieve_threshold(), 1)


if __name__ == '__main__':
    unittest.main()
