from unittest import TestCase
from contracting.client import ContractingClient


def action_core():
    # Convenience
    I = importlib

    S = Hash()
    actions = Hash()
    owner = Variable()

    # Policy interface
    action_interface = [
        I.Func('interact', args=('payload', 'state', 'caller')),
    ]

    @construct
    def seed():
        owner.set(ctx.caller)

    @export
    def change_owner(new_owner: str):
        assert ctx.caller == owner.get(), 'Only owner can call!'
        owner.set(new_owner)

    @export
    def register_action(action: str, contract: str):
        assert ctx.caller == owner.get(), 'Only owner can call!'
        assert actions[action] is None, 'Action already registered!'
        # Attempt to import the contract to make sure it is already submitted
        p = I.import_module(contract)

        # Assert ownership is election_house and interface is correct
        assert I.owner_of(p) == ctx.this, \
            'This contract must control the action contract!'

        assert I.enforce_interface(p, action_interface), \
            'Action contract does not follow the correct interface!'

        actions[action] = contract

    @export
    def unregister_action(action: str):
        assert ctx.caller == owner.get(), 'Only owner can call!'
        assert actions[action] is not None, 'Action does not exist!'

        actions[action] = None

    @export
    def interact(action: str, payload: dict):
        contract = actions[action]
        assert contract is not None, 'Invalid action!'

        module = I.import_module(contract)

        result = module.interact(payload, S, ctx.caller)
        return result

    @export
    def bulk_interact(action: str, payloads: list):
        for payload in payloads:
            interact(action, payload)


def example_action():
    @export
    def interact(payload: dict, state: Any, caller: str):
        state[payload['key']] = payload['value']


def bad_action():
    @export
    def not_interact(payload: dict, state: Any, caller: str):
        state[payload['key']] = payload['value']


class TestActionCore(TestCase):
    def setUp(self):
        self.client = ContractingClient()
        self.client.flush()
        self.client.submit(action_core, name='action_core')

        self.action_core = self.client.get_contract(name='action_core')

    def tearDown(self):
        self.client.flush()

    def test_submit_sets_owner(self):
        self.assertEqual(self.action_core.owner.get(), 'sys')

    def test_change_owner_as_sys_works(self):
        self.action_core.change_owner(new_owner='stu')
        self.assertEqual(self.action_core.owner.get(), 'stu')

    def test_change_not_as_owner_fails(self):
        with self.assertRaises(AssertionError):
            self.action_core.change_owner(new_owner='stu', signer='not_sys')

    def test_register_works_if_all_asserts_pass(self):
        self.client.submit(example_action, owner='action_core')
        self.action_core.register_action(action='thing', contract='example_action')

    def test_register_action_fails_if_not_owner(self):
        with self.assertRaises(AssertionError):
            self.action_core.register_action(action='thing', contract='another_thing', signer='not_sys')

    def test_register_action_fails_if_contract_doesnt_exist(self):
        with self.assertRaises(ImportError):
            self.action_core.register_action(action='thing', contract='doesnt_exist')

    def test_register_action_fails_if_contract_not_owner(self):
        self.client.submit(example_action)

        with self.assertRaises(AssertionError):
            self.action_core.register_action(action='thing', contract='example_action')

    def test_register_action_fails_if_action_doesnt_adhere_to_interface(self):
        self.client.submit(bad_action, owner='action_core')
        with self.assertRaises(AssertionError):
            self.action_core.register_action(action='thing', contract='bad_action')

    def test_register_action_fails_if_action_already_registered(self):
        self.client.submit(example_action, owner='action_core')
        self.action_core.register_action(action='thing', contract='example_action')
        with self.assertRaises(AssertionError):
            self.action_core.register_action(action='thing', contract='example_action')

    def test_unregister_works_if_no_asserts_hit(self):
        self.client.submit(example_action, owner='action_core')
        self.action_core.register_action(action='thing', contract='example_action')
        self.action_core.unregister_action(action='thing')

        # Returns AttributeError because the key was deleted and there was only one that existed, so to the driver,
        # the hash doesn't exist. This should be fixed.
        with self.assertRaises(AttributeError):
            self.action_core.actions['thing']

    def test_unregister_fails_if_not_owner(self):
        self.client.submit(example_action, owner='action_core')
        self.action_core.register_action(action='thing', contract='example_action')
        with self.assertRaises(AssertionError):
            self.action_core.unregister_action(action='thing', signer='not_sys')

    def test_unregister_fails_if_action_doesnt_exist(self):
        self.client.submit(example_action, owner='action_core')
        with self.assertRaises(AssertionError):
            self.action_core.unregister_action(action='thing')

    def test_interact_fails_if_no_action_registerred(self):
        self.client.submit(example_action, owner='action_core')

        payload = {
            'key': 'test',
            'value': 'blah'
        }

        with self.assertRaises(AssertionError):
            self.action_core.interact(action='thing', payload=payload)

    def test_interact_writes_to_base_state(self):
        self.client.submit(example_action, owner='action_core')
        self.action_core.register_action(action='thing', contract='example_action')

        payload = {
            'key': 'test',
            'value': 'blah'
        }

        self.action_core.interact(action='thing', payload=payload)

        self.assertEqual(self.action_core.S['test'], 'blah')

    def test_bulk_interact_does_multiple_writes_to_base_state(self):
        self.client.submit(example_action, owner='action_core')
        self.action_core.register_action(action='thing', contract='example_action')

        payloads = [
            {'key': 'test1', 'value': 'blah1'},
            {'key': 'test2', 'value': 'blah2'},
            {'key': 'test3', 'value': 'blah3'}
        ]

        self.action_core.bulk_interact(action='thing', payloads=payloads)

        self.assertEqual(self.action_core.S['test1'], 'blah1')
        self.assertEqual(self.action_core.S['test2'], 'blah2')
        self.assertEqual(self.action_core.S['test3'], 'blah3')

    def test_multiple_actions_registered_to_same_contract_works(self):
        self.client.submit(example_action, owner='action_core')
        self.action_core.register_action(action='thing1', contract='example_action')
        self.action_core.register_action(action='thing2', contract='example_action')

        payload = {
            'key': 'test1',
            'value': 'blah1'
        }

        self.action_core.interact(action='thing1', payload=payload)

        payload = {
            'key': 'test2',
            'value': 'blah2'
        }

        self.action_core.interact(action='thing2', payload=payload)

        self.assertEqual(self.action_core.S['test1'], 'blah1')
        self.assertEqual(self.action_core.S['test2'], 'blah2')
