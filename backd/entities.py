from __future__ import annotations

import datetime as dt
import pickle
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterator, List, Set, Type, TypeVar

from .base_factory import BaseFactory


@dataclass(order=True)
class PointInTime:
    block_number: int
    transaction_index: int
    log_index: int

    @classmethod
    def from_event(cls, event: dict) -> "PointInTime":
        return cls(
            block_number=event["blockNumber"],
            transaction_index=event["transactionIndex"],
            log_index=event["logIndex"],
        )


@dataclass
class UserBalances:
    total_borrowed: int = 0
    token_balance: int = 0


@dataclass
class Balances(UserBalances):
    total_underlying: int = 0


@dataclass
class MarketUser:
    balances: UserBalances = None
    entered: bool = False
    borrow_index: int = 10 ** 18

    def __post_init__(self):
        if self.balances is None:
            self.balances = UserBalances()

    def borrowed_at(self, market_index: int) -> int:
        return self.balances.total_borrowed * market_index // self.borrow_index


@dataclass(eq=False, repr=False)
class Market:
    address: str
    interest_rate_model: str = None
    balances: Balances = None
    reserve_factor: Decimal = Decimal("0")
    collateral_factor: Decimal = Decimal("0")
    users: Dict[str, MarketUser] = None
    listed: bool = False
    comptroller_address: str = None
    reserves: int = 0
    borrow_index: int = 10 ** 18

    def __post_init__(self):
        self.address = self.address.lower()
        if self.balances is None:
            self.balances = Balances()
        if self.users is None:
            self.users = defaultdict(MarketUser)

    def get_cash(self):
        return self.balances.total_underlying

    @property
    def underlying_exchange_rate(self):
        if self.balances.token_balance == 0:
            return 0
        numerator = self.get_cash() + self.balances.total_borrowed - self.reserves
        return numerator * 10 ** 18 // self.balances.token_balance

    def compute_new_total_borrowed(self, new_index: int) -> int:
        return self.balances.total_borrowed * new_index // self.borrow_index

    def __eq__(self, other):
        return self.address == other.address

    def __hash__(self):
        return hash(self.address)

    def __repr__(self):
        return f"Market(address='{self.address}')"


@dataclass
class Markets:
    markets: List[Market]

    def __init__(self, markets: List[Market] = None):
        if markets is None:
            markets = []
        self.markets = markets

    def find_by_address(self, address: str) -> Market:
        normalized_address = address.lower()
        for market in self.markets:
            if market.address == normalized_address:
                return market
        raise ValueError(f"could not find market with address {address}")

    def add_market(self, new_market: Market):
        if any(market == new_market for market in self.markets):
            raise ValueError(f"market {new_market} already exists")
        self.markets.append(new_market)

    def __getitem__(self, key):
        return self.markets[key]

    def __len__(self):
        return len(self.markets)

    def __iter__(self) -> Iterator[Market]:
        return iter(self.markets)


@dataclass
class Oracle(BaseFactory):
    markets: Markets
    prices: Dict[str, int] = None

    def __post_init__(self):
        if self.prices is None:
            self.prices = {}

    def update_price(self, token: str, price: int, inverted: bool = False):
        if inverted and price > 0:
            price = 10 ** 36 // price
        self.prices[token.lower()] = price

    def get_price(self, token: str) -> int:
        return self.prices.get(token.lower(), 0)


@dataclass
class Oracles:
    markets: Markets
    oracles: Dict[str, Oracle] = None
    current_address: str = None

    def __post_init__(self):
        if self.oracles is None:
            self.oracles = {}

    def get_oracle(self, oracle_address: str) -> Oracle:
        oracle_address = oracle_address.lower()
        if oracle_address not in self.oracles:
            self.create_oracle(oracle_address)
        return self.oracles[oracle_address]

    def create_oracle(self, oracle_address: str):
        oracle_class = Oracle.get(oracle_address)
        oracle = oracle_class(self.markets)
        self.oracles[oracle_address] = oracle

    def __len__(self):
        return len(self.oracles)

    @property
    def current(self) -> Oracle:
        return self.oracles[self.current_address]


@dataclass
class State:
    protocol_name: str
    current_event_time: PointInTime = None
    last_event_time: PointInTime = None
    timestamp: dt.datetime = None
    markets: Markets = None
    oracles: Oracles = None
    extra: dict = None  # used by hooks to persist data to state

    def compute_unique_users(self) -> Set[str]:
        users = set()
        for market in self.markets:
            users |= market.users.keys()
        return users

    def __post_init__(self):
        if self.markets is None:
            self.markets = Markets()
        if self.oracles is None:
            self.oracles = Oracles(self.markets)
        if self.extra is None:
            self.extra = {}

    @classmethod
    def load(cls: Type[T], filepath: str) -> T:
        with open(filepath, "rb") as f:
            return pickle.load(f)


T = TypeVar("T", bound=State)
