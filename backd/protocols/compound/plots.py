import datetime as dt

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cycler import cycler
from matplotlib.ticker import FuncFormatter

from ... import constants, db
from ...plot_utils import COLORS, DEFAULT_PALETTE
from .entities import CompoundState
from .hooks import (
    Borrowers,
    LiquidationAmounts,
    LiquidationAmountsWithTime,
    Suppliers,
    UsersBorrowSupply,
)

INT_FORMATTER = FuncFormatter(lambda x, _: "{:,}".format(int(x)))
LARGE_MONETARY_FORMATTER = FuncFormatter(lambda x, _: "{:,}M".format(x // 1e6))

mpl.rcParams["axes.prop_cycle"] = cycler(color=DEFAULT_PALETTE)
mpl.rcParams["font.size"] = 14


def plot_suppliers_borrowers_over_time(args: dict):
    state = CompoundState.load(args["state"])
    block_dates = db.get_block_dates()

    def get_users(history):
        return [
            (block, count)
            for block, count in history.items()
            if count > 0 and block in block_dates
        ]

    def get_xy(users, interval):
        x = [block_dates[v[0]] for v in users[::interval]]
        y = [v[1] for v in users[::interval]]
        return x, y

    suppliers = get_users(state.extra[Suppliers.extra_key].historical_count)
    borrowers = get_users(state.extra[Borrowers.extra_key].historical_count)
    interval = args["interval"]

    x1, y1 = get_xy(borrowers, interval)
    x2, y2 = get_xy(suppliers, interval)

    plt.xticks(rotation=45)
    plt.xlabel("Date")
    plt.ylabel("Number of accounts")
    plt.plot(x1, y1, "-", label="Borrowers")
    plt.plot(x2, y2, "-", label="Suppliers")
    ax = plt.gca()
    ax.yaxis.set_major_formatter(INT_FORMATTER)
    plt.tight_layout()
    plt.legend(loc="upper left")

    output_plot(args.get("output"))


def plot_supply_borrow_over_time(args: dict):
    state = CompoundState.load(args["state"])
    supply_borrows = state.extra["supply-borrow"].set_index("timestamp")

    sampling_period = args["resample"]
    key_mapping = {
        "borrows": "Total borrowed",
        "supply": "Total supply",
        "underlying": "Total locked",
    }
    for key, new_key in key_mapping.items():
        supply_borrows[new_key] = supply_borrows[key] / 1e18

    # TODO: check this is actually doing mean per market
    # within a time bin and then summing all the means
    means = (
        supply_borrows.groupby("market").resample(sampling_period).mean().sum(level=1)
    )
    ax = means[list(key_mapping.values())].plot()
    ax.yaxis.set_major_formatter(LARGE_MONETARY_FORMATTER)
    ax.set_ylabel("Amount (USD)")
    ax.set_xlabel("Date")
    plt.tight_layout()
    output_plot(args.get("output"))


def plot_liquidable_over_time(args: dict):
    ax = plt.gca()
    styles = args["styles"]

    max_value = 0
    for i, filepath in enumerate(args["files"]):
        df = pd.read_csv(filepath, parse_dates=[0]).set_index("timestamp")
        label = args["labels"][i]
        df.resample(args["resample"]).max().value.plot(
            style=styles[i], ax=ax, label=label
        )
        max_value = max(df.value.max(), max_value)
    ax.set_ylim((0, int(max_value * 1.1)))
    x_start, x_end = ax.get_xlim()
    expand = (x_end - x_start) * 0.05
    ax.set_xlim((x_start - expand, x_end + expand))
    ax.yaxis.set_major_formatter(LARGE_MONETARY_FORMATTER)
    ax.vlines(
        dt.datetime(2020, 6, 15), *ax.get_ylim(), colors=COLORS["gray"], linestyles="--"
    )
    ax.set_ylabel("Liquidable amount (USD)")
    ax.set_xlabel("Date")
    ax.tick_params(axis="x", rotation=45)
    plt.legend(loc="upper left")

    plt.tight_layout(pad=1.2)

    output_plot(args["output"])


def plot_supply_borrow_ratios_over_time(args: dict):
    state = CompoundState.load(args["state"])
    block_dates = db.get_block_dates()
    users_borrow_supply = state.extra[UsersBorrowSupply.extra_key]

    blocks = [block for block in users_borrow_supply if block in block_dates]
    x = [block_dates[block] for block in blocks]

    thresholds = args["thresholds"]
    labels = ["< {0:.2f}%".format(t * 100) for t in thresholds]
    labels.append("$\\geq$ {0:.2f}%".format(thresholds[-1] * 100))

    block_buckets = []
    total_supplies = []
    for block in blocks:
        users = users_borrow_supply[block]
        buckets = [0] * (len(thresholds) + 1)
        total = 0
        for supply, borrow in users.values():
            normalized_supply = supply / constants.DEFAULT_DECIMALS
            total += normalized_supply
            if borrow == 0:
                ratio = 1000
            else:
                ratio = supply / borrow
            for i, value in enumerate(thresholds):
                # only add to first valid bucket
                if ratio < value:
                    buckets[i] += normalized_supply
                    break
            else:
                buckets[-1] += normalized_supply
        total_supplies.append(total)
        block_buckets.append(buckets)

    ys = list(zip(*block_buckets))

    plt.xticks(rotation=45)
    plt.xlabel("Date")
    plt.ylabel("Supply in USD")
    # plt.plot_date(x, total_supplies, fmt="-")
    plt.stackplot(x, *ys, labels=labels, colors=DEFAULT_PALETTE)
    ax = plt.gca()
    ax.yaxis.set_major_formatter(LARGE_MONETARY_FORMATTER)
    plt.legend(title="Collateral/borrow ratio", loc="upper left")
    plt.tight_layout()
    output_plot(args.get("output"))


def plot_liquidations_over_time(args: dict):
    state = CompoundState.load(args["state"])
    liquidation_info = state.extra[LiquidationAmounts.extra_key]
    group_key = liquidation_info.timestamp.dt.floor("d")

    liquidation_info["eth_price_usd"] = liquidation_info.eth_price.astype(float) / 1e18
    eth_price = liquidation_info.groupby(group_key).eth_price_usd.mean()
    amounts = liquidation_info.groupby(group_key).usd_seized.sum() / 1e18

    ax = plt.gca()
    l1 = ax.plot_date(amounts.index, amounts.values, fmt="-", color=DEFAULT_PALETTE[1])
    ax.set_ylabel("Amount liquidated (USD)")
    ax.yaxis.set_major_formatter(LARGE_MONETARY_FORMATTER)
    ax.tick_params(axis="x", rotation=45)

    ax2 = ax.twinx()
    l2 = ax2.plot_date(
        eth_price.index, eth_price.values, fmt="--", color=DEFAULT_PALETTE[0]
    )
    ax2.set_ylabel("ETH price (USD)")
    ax2.set_ylim((0, 500))

    ax.set_xlabel("Date")
    ax.legend(l1 + l2, ["Amount liquidated", "ETH price"], loc="upper left")

    plt.tight_layout()
    output_plot(args.get("output"))


def plot_supply_borrow_distribution(args: dict):
    state = CompoundState.load(args["state"])
    users = state.compute_unique_users()
    prop = args["property"]

    values = []
    threshold = args["threshold"]
    for user in users:
        total_supply, total_borrow = state.compute_user_position(user, False)
        value = total_supply if prop == "supply" else total_borrow
        if value > threshold * 10 ** 18:
            values.append(value / 1e18)

    bucket_size = args["bucket_size"]
    total = sum(values)
    values = sorted(values)
    padding = [0] * (bucket_size - len(values) % bucket_size)
    values = np.array(padding + values)
    values = np.sum(values.reshape(-1, bucket_size), axis=1)
    cum_values = [sum(values[:i]) for i in range(0, len(values) + 1)]

    heights = [v / total for v in cum_values]
    interval = args["interval"]

    x = np.arange(len(heights))
    xticks = x[::interval]
    if x[-1] - xticks[-1] < (xticks[1] - xticks[0]) / 2:
        xticks = xticks[:-1]
    ticks = np.append(xticks, x[-1])

    ax1 = plt.gca()
    ax1.bar(x, heights, width=1.0, color=COLORS["gray"])

    ax1.set_yticks(list(ax1.get_yticks())[:-1])
    ax1.set_yticklabels(["{0:,}".format(int(total * v)) for v in ax1.get_yticks()])
    ax1.set_ylabel("Cumulative amount of USD")
    ax1.set_xticks(ticks)

    ax1.set_xlabel("Number of users")
    ax1.tick_params(axis="x", rotation=45)

    ax2 = ax1.twinx()
    ax2.bar(x, heights, width=1.0, color=COLORS["gray"])

    ax2.set_yticks(list(ax2.get_yticks())[:-1])  # use FixedLocator
    ax2.set_yticklabels(["{0}%".format(int(v * 100)) for v in ax2.get_yticks()])
    ax2.set_ylabel("Cumulative percentage of USD")

    ax2.set_xticks(ticks)
    ax2.set_xticklabels(ticks * bucket_size)

    plt.tight_layout()

    output_plot(args["output"])


def plot_time_to_liquidation(args: dict):
    state = CompoundState.load(args["state"])
    data = state.extra[LiquidationAmountsWithTime.extra_key]
    seized_by_ellapsed = data.groupby("block_ellapsed").sum().usd_seized
    max_blocks = args["max_blocks"]
    selected_blocks = seized_by_ellapsed.iloc[:max_blocks]
    cumsum = selected_blocks.cumsum() / 1e18

    print(f"covered: {selected_blocks.sum() / data.usd_seized.sum()}%")

    x = cumsum.index
    heights = cumsum.values

    ax1 = plt.gca()
    ax1.set_xticks(x)
    ax1.bar(x, heights, width=1.0, color=COLORS["gray"])
    ax1.set_xlabel("Number of blocks elapsed")
    ax1.set_ylabel("Amount of USD")
    ax1.yaxis.set_major_formatter(LARGE_MONETARY_FORMATTER)
    ax2 = ax1.twinx()
    ax2.set_yticks(list(range(0, 101, 20)))
    ax2.set_yticklabels(["{0}%".format(v) for v in ax2.get_yticks()])
    ax2.set_ylabel("Percentage of USD")

    plt.tight_layout()

    output_plot(args["output"])


def output_plot(output: str = None):
    if output is None:
        plt.show()
    else:
        plt.savefig(output)


def plot_top_suppliers_and_borrowers(args: dict):
    state = CompoundState.load(args["state"])
    users = state.compute_unique_users()

    borrows = []
    supplies = []
    for user in users:
        total_supplied, total_borrowed = state.compute_user_position(user, False)
        supplies.append((user, total_supplied / constants.DEFAULT_DECIMALS))
        borrows.append((user, total_borrowed / constants.DEFAULT_DECIMALS))

    supplies.sort(key=lambda x: -x[1])
    borrows.sort(key=lambda x: -x[1])

    def output(accounts):
        for address, value in accounts:
            print(address, "&", f"{round(value):,}")

    print("Suppliers")
    output(supplies[: args.get("n", 10)])
    print("Borrowers")
    output(borrows[: args.get("n", 10)])
