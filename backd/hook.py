from typing import List, Union

from .base_factory import BaseFactory
from .entities import State


class Hook(BaseFactory):
    def global_start(self, state: State):
        pass

    def global_end(self, state: State):
        pass

    def block_start(self, state: State, block_number: int):
        pass

    def block_end(self, state: State, block_number: int):
        pass

    def transaction_start(
        self, state: State, block_number: int, transaction_index: int
    ):
        pass

    def transaction_end(self, state: State, block_number: int, transaction_index: int):
        pass

    def event_start(self, state: State, event: dict):
        pass

    def event_end(self, state: State, event: dict):
        pass


class Hooks:
    def __init__(self, hooks: List[Union[Hook, str]] = None):
        if hooks is None:
            hooks = []
        self.hooks = []
        for hook in hooks:
            if isinstance(hook, str):
                hook = Hook.get(hook)()
            self.hooks.append(hook)
        self._last_block = None
        self._last_transaction = None

    def execute_hooks_start(self, state: State, event: dict):
        if self._last_transaction != state.current_event_time.transaction_index:
            for hook in self.hooks:
                hook.transaction_end(state, self._last_block, self._last_transaction)

        if self._last_block != state.current_event_time.block_number:
            for hook in self.hooks:
                hook.block_end(state, self._last_block)
            self._last_block = state.current_event_time.block_number
            for hook in self.hooks:
                hook.block_start(state, self._last_block)

        if self._last_transaction != state.current_event_time.transaction_index:
            self._last_transaction = state.current_event_time.transaction_index
            for hook in self.hooks:
                hook.transaction_start(state, self._last_block, self._last_transaction)

        for hook in self.hooks:
            hook.event_start(state, event)

    def execute_hooks_end(self, state: State, event: dict):
        for hook in self.hooks:
            hook.event_end(state, event)

    def initialize_hooks(self, state: State):
        for hook in self.hooks:
            hook.global_start(state)

    def finalize_hooks(self, state: State):
        for hook in self.hooks:
            hook.transaction_end(state, self._last_block, self._last_transaction)
        for hook in self.hooks:
            hook.block_end(state, self._last_block)
        for hook in self.hooks:
            hook.global_end(state)
