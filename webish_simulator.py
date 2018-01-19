# FIXME: datetime.now() has to be replaced with the last monday at 0:00
# TODO: crear df de 30 días y meterle la semana sintética tantas veces como entre
# TODO: ya no es necesario trabajar con datetimes

import awscosts
import pandas as pd
import datetime
import numpy as np


def simulate(df: pd.DataFrame, monthly_scale_factor=None):

    # prepare DF fields
    df['hits'] = df['hits'].astype(float)
    df['weekday'] = df.index.weekday_name
    df['hour'] = df.index.hour

    startdate = datetime.datetime(1970, 1, 5)
    days = ('Monday', 'Tuesday', 'Wednesday', 'Thursday',
            'Friday', 'Saturday', 'Sunday')

    week_df = pd.DataFrame()

    for day in days:
        aux_df = pd.DataFrame(
            index=pd.date_range(start=startdate, periods=24, freq='H'),
            columns=['requests']
        )

        # Create a list of average hits for each hour in a given weekday:
        hitmeans = df.loc[df['weekday'] == day].groupby('hour')['hits'].mean()
        aux_df['requests'] = np.array(hitmeans).round().astype(int)
        startdate += datetime.timedelta(days=1)
        week_df = pd.concat([week_df, aux_df])

    # Build month DataFrame from week DF
    month_df = pd.DataFrame(
        index=pd.date_range(
            start=datetime.datetime(2018, 1, 1), periods=28 * 24, freq='H'
        )
    )
    month_df['requests'] = list(week_df['requests']) * 4
    total_month_hits = float(month_df['requests'].sum())
    month_df['reqs_normalized'] = \
        month_df['requests'] / total_month_hits

    if monthly_scale_factor is not None:
        month_df['requests'] = \
            month_df['reqs_normalized'] * monthly_scale_factor
        month_df = month_df.round({'requests': 0})
        month_df['requests'] = month_df['requests'].astype(int)

    return month_df


def get_lambda_cost(df: pd.DataFrame, MB_per_request=128, ms_per_req=200,):
    mylambda = awscosts.Lambda(
        MB_per_req=MB_per_request,
        ms_per_req=ms_per_req
    )

    df['lambda_cost'] = df.apply(
        lambda x: mylambda.get_cost(reqs=x['requests']),
        axis=1
    )

    df['lambda_sum'] = df.lambda_cost.cumsum()
    df = df.round({'lambda_cost': 2, 'lambda_sum': 2})

    return df


def get_ec2_cost(df: pd.DataFrame, instance_type, max_reqs_per_second):
    myec2 = awscosts.EC2(
        instance_type=instance_type,
        max_reqs_per_second=max_reqs_per_second
    )
    df['ec2_cost'] = df.apply(
        lambda x: myec2.get_cost_and_num_instances(3600, reqs=x['requests'])[0],
        axis=1
    )

    df['instances'] = df.apply(
        lambda x: myec2.get_num_instances(reqs=x['requests'] / 3600),
        axis=1
    )

    df['ec2_sum'] = df.ec2_cost.cumsum()
    df = df.round({'ec2_cost': 2, 'ec2_sum': 2})

    return df


def find_breakeven(df: pd.DataFrame):
    df['req_sum'] = df.requests.cumsum()
    breakeven_df = df[df.break_even < 0]
    if breakeven_df.empty:
        return None
    return breakeven_df.iloc[0]


def get_breakeven(df: pd.DataFrame, factor_list: list):
    # simulate and calculate costs for several factors:
    breakeven_points = list()
    for factor in factor_list:
        month_df = simulate(df, monthly_scale_factor=factor)
        month_df = get_lambda_cost(
            month_df,
            MB_per_request=256,
            ms_per_req=200,
        )
        month_df = get_ec2_cost(
            month_df,
            instance_type='m3.medium',
            max_reqs_per_second=1000
        )
        month_df['break_even'] = month_df['ec2_sum'] - month_df['lambda_sum']

        breakeven = find_breakeven(month_df)
        if breakeven is not None:
            breakeven_points.append((breakeven['req_sum'] / factor) * 100)
        else:
            breakeven_points.append(100)
    mean_reqs_per_second = [x / float(28 * 24 * 60 * 60) for x in factor_list]

    return mean_reqs_per_second, breakeven_points
