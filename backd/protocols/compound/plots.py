import matplotlib as mpl
import matplotlib.pyplot as plt
from cycler import cycler
from matplotlib.ticker import FuncFormatter

from ... import constants, db
from ...plot_utils import DEFAULT_PALETTE
from .entities import CompoundState
from .hooks import Borrowers, LiquidationAmounts, Suppliers, UsersBorrowSupply

INT_FORMATTER = FuncFormatter(lambda x, _: "{:,}".format(int(x)))
LARGE_MONETARY_FORMATTER = FuncFormatter(lambda x, _: "{:,}M".format(x // 1e6))

mpl.rcParams["axes.prop_cycle"] = cycler(color=DEFAULT_PALETTE)


def plot_borrowers_over_time(args: dict):
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
    if args["options"] and "interval" in args["options"]:
        interval = int(args["options"]["interval"])
    else:
        interval = 100

    x1, y1 = get_xy(suppliers, interval)
    x2, y2 = get_xy(borrowers, interval)

    plt.xticks(rotation=45)
    plt.xlabel("Date")
    plt.ylabel("Count")
    plt.plot(x1, y1, "-", label="Suppliers")
    plt.plot(x2, y2, "-", label="Borrowers")
    ax = plt.gca()
    ax.yaxis.set_major_formatter(INT_FORMATTER)
    plt.tight_layout()
    plt.legend()

    output_plot(args.get("output"))


def plot_supply_borrow_over_time(args: dict):
    state = CompoundState.load(args["state"])
    block_dates = db.get_block_dates()
    users_borrow_supply = state.extra[UsersBorrowSupply.extra_key]

    blocks = [block for block in users_borrow_supply if block in block_dates]
    x = [block_dates[block] for block in blocks]

    if args["options"] and "thresholds" in args["options"]:
        thresholds = [float(v) for v in args["options"]["thresholds"].split(",")]
    else:
        thresholds = [1.0, 1.05, 1.1, 1.25, 1.5, 2.0]
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
    plt.ylabel("Collateral in USD")
    # plt.plot_date(x, total_supplies, fmt="-")
    plt.stackplot(x, *ys, labels=labels, colors=DEFAULT_PALETTE)
    ax = plt.gca()
    ax.yaxis.set_major_formatter(LARGE_MONETARY_FORMATTER)
    plt.legend(title="Supply/borrow ratio", loc="upper left")
    plt.tight_layout()
    output_plot(args.get("output"))


def plot_liquidations_over_time(args: dict):
    state = CompoundState.load(args["state"])
    liquidation_info = state.extra[LiquidationAmounts.extra_key]
    group_key = liquidation_info.timestamp.dt.floor("d")

    counts = liquidation_info.groupby(group_key).size()
    amounts = liquidation_info.groupby(group_key).usd_seized.sum() / 1e18

    ax = plt.gca()
    l1 = ax.plot_date(counts.index, counts.values, fmt="--", color=DEFAULT_PALETTE[0])
    plt.xticks(rotation=45)
    ax.set_ylabel("Number of liquidations")
    ax.set_xlabel("Date")
    ax2 = ax.twinx()
    l2 = ax2.plot_date(amounts.index, amounts.values, fmt="-", color=DEFAULT_PALETTE[1])
    ax2.set_ylabel("Amount liquidated (USD)")
    ax2.yaxis.set_major_formatter(LARGE_MONETARY_FORMATTER)
    ax.legend(l1 + l2, ["Count", "Amount"], loc="upper left")
    plt.tight_layout()
    output_plot(args.get("output"))


def output_plot(output: str = None):
    if output is None:
        plt.show()
    else:
        plt.savefig(output)
