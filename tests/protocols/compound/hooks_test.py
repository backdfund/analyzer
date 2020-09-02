from decimal import Decimal as D

from backd.protocols.compound.hooks import DSRHook
from backd.entities import Market, State, PointInTime, Balances
from backd import constants


def test_dsr_hook():
    state = State("compound")
    state.current_event_time = PointInTime(99, 1, 1)
    hook = DSRHook([
        {"block": 100, "rate": D("1.0") * 10 ** constants.DSR_DECIMALS},
        {"block": 105, "rate": D("1.1") * 10 ** constants.DSR_DECIMALS},
        {"block": 110, "rate": D("1.5") * 10 ** constants.DSR_DECIMALS},
    ])

    state.markets.add_market(Market("0x1234", balances=Balances(total_supplied=10)))
    hook.run(state)
    assert state.markets.find_by_address("0x1234").balances.total_supplied == 10

    cdai_market = Market(constants.CDAI_ADDRESS, balances=Balances(total_supplied=10))
    state.markets.add_market(cdai_market)
    hook.run(state)
    assert cdai_market.balances.total_supplied == 10

    state.current_event_time = PointInTime(105, 1, 1)
    hook.run(state)
    assert cdai_market.balances.total_supplied == 11

    state.current_event_time = PointInTime(106, 1, 1)
    hook.run(state)
    assert cdai_market.balances.total_supplied == 12

    state.current_event_time = PointInTime(110, 1, 1)
    hook.run(state)
    assert cdai_market.balances.total_supplied == 18