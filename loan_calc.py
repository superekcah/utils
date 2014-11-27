#!/usr/bin/python

from datetime import datetime
import math

BASE_INTEREST_RATES = [
    (datetime(2008, 12, 23), 5.94),
    (datetime(2010, 10, 20), 6.14),
    (datetime(2010, 12, 26), 6.40),
    (datetime(2011, 2, 9), 6.60),
    (datetime(2011, 4, 6), 6.80),
    (datetime(2011, 7, 7), 7.05),
    (datetime(2012, 6, 8), 6.80),
    (datetime(2012, 7, 6), 6.55),
    (datetime(2014, 11, 22), 6.15)
]


def get_interest_rate(year, month, day, rates=BASE_INTEREST_RATES):
    arg_date = datetime(year, month, day)
    if len(rates) < 2:
        s_date, s_rate = rates[0]
        if arg_date > s_date:
            return s_rate
        else:
            raise Exception("Cannot get base interest rate!")
    else:
        size = len(rates)
        mid = int((size + 1) / 2)
        s_date, s_rate = rates[mid]
        if arg_date > s_date:
            return get_interest_rate(year, month, day, rates[mid:])
        else:
            return get_interest_rate(year, month, day, rates[:mid])


def get_fixed_month_rate(year, month):
    cur_year_rate = get_interest_rate(year, 1, 1)
    if month == 1:
        last_year_rate = get_interest_rate(year - 1, 1, 1)
        return (last_year_rate * 0.8 + cur_year_rate * 0.2) / 12 * 0.85
    else:
        return cur_year_rate * 0.85 / 12


def calc_amortization_payment(total_amount, interest_rate, remain_months):
    im = math.pow((1 + interest_rate / 100), remain_months)
    ap = total_amount * interest_rate * im / (im - 1) / 100
    return ap


def calc_payment_list(start_year, start_meonth, total_months, total_amount,
                      n=None):
    if not n:
        n = total_months
    last_rate = get_fixed_month_rate(start_year, start_meonth)
    ap = calc_amortization_payment(total_amount, last_rate, total_months)
    rate = last_rate
    year = start_year
    month = start_meonth
    rate_changed = False
    for i in range(0, n):
        if rate_changed:
            rate = get_fixed_month_rate(year, month)
            last_rate = rate
            ap = calc_amortization_payment(total_amount, rate,
                                           total_months - i)
            rate_changed = False
        if month == 1:
            rate = get_fixed_month_rate(year, month)
            if rate != last_rate:
                rate_changed = True
                ap = calc_amortization_payment(total_amount, rate,
                                               total_months - i)
        ip = total_amount * rate / 100
        pp = ap - ip
        total_amount -= pp
        print("%d-%d: pay %.2f (%.2f / %.2f), remain: %.2f"
              % (year, month, ap, pp, ip, total_amount))
        month += 1
        if month == 13:
            year += 1
            month = 1


def main():
    calc_payment_list(2010, 2, 360, 1390000, 70)


if __name__ == '__main__':
    main()
