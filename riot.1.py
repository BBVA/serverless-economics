from functools import reduce, partial
from itertools import accumulate
from iot.simulator import *
from random import randint
import plotly
import plotly.plotly as py
import plotly.graph_objs as go
import numpy as np
import awscosts

def generate_requests_time_serie(num_devices, request_period, interval_duration, resolution):
    mean = num_devices // request_period
    result = list()
    for i in range(0,(interval_duration//resolution)):
        if i > 0 and i < 1000:
            result.append(mean/2)
        if i >= 1000 and i < 1500:
            result.append(mean*2)
        if i >=1500 and i < 6500:
            result.append(mean/2)
        if i >= 6500 and i <8000:
            result.append(mean*2)
        if i >=8000:
            result.append(mean/2)
    return result
    #return [num_devices // request_period] * (interval_duration//resolution)

def aggregate_costs(req_period, resolution, interval_duration, num_devices, lambda_instance, ec2_instances_list, devices_time_serie):
    costs = {'resolution_buckets':0, 'hits':0, 'lambda':0}
    costs['resolution_buckets'] = interval_duration // resolution
    costs['hits'] = num_devices * (interval_duration // req_period)
    costs['reqs_per_second'] = costs['hits'] / interval_duration
    costs['lambda'] = lambda_instance.get_cost(costs['hits'], reset_free_tier=True)

    def calc_ec2_instance_use(num_hits, ec2_instance = None, resolution = 0):
        num_instances = max(1,ec2_instance.get_num_instances(num_hits)) # the cost of one fixed instance plus the cost of the auto-scaled ones
        cost = (ec2_instance._cost_per_hour/3600) * resolution *  num_instances # we accumulate only auto-scaled instances (>1)
        return (num_instances, cost)
    
    for ec2_instance in ec2_instances_list:
        calc_by_instance = partial(calc_ec2_instance_use, ec2_instance = ec2_instance, resolution = resolution)
        instances,cost = reduce(lambda x, y:  (max(x[0],y[0]), x[1] + y[1]), map(calc_by_instance, devices_time_serie), (0, 0))
        costs.update({
            f'ec2_{ec2_instance._instance_type}_cost':cost,
            f'ec2_{ec2_instance._instance_type}_instances': instances
            })
    
    return costs

def draw_costs_by_num_devices(costs, num_devices_list, ec2_flavors, req_period):

    data = []

    lambda_trace = go.Scatter(
        x=[cost["reqs_per_second"] for cost in costs],
        y=[cost['lambda'] for cost in costs],
        name='Lambda'
    )
    data.append(lambda_trace)

    for flavor in ec2_flavors:
        trace1 = go.Scatter(
            x=[cost["reqs_per_second"] for cost in costs],
            y=[cost[f'ec2_{flavor}_cost'] for cost in costs],
            name=f'EC2 {flavor}',
            showlegend=False
        )
        trace2 = go.Scatter(
            x=num_devices_list,
            y=[cost[f'ec2_{flavor}_cost'] for cost in costs],
            name=f'EC2 {flavor}',
            xaxis='x2'
        )
        data.append(trace1)
        data.append(trace2)

    layout = go.Layout(
        title=f'Cost by number of devices (request period: {req_period} seconds)',
        legend=dict(orientation='h'),
        width=1000,
        height=800,
        margin=go.Margin(
            t=200,
            b=200,
            r=100,
            l=100,
            autoexpand=False
        ),
        xaxis=dict(
            title='Number of reqs/sec',
            type='log',
            anchor='free',
            position=0.02
        ),
        xaxis2=dict(
            title="Number of devices",
            type='log',
            side='top',
            overlaying='x'
        ),
        yaxis=dict(
            title='Cost ($)'
        )
    )

    fig = go.Figure(data=data, layout=layout)
    plotly.offline.plot(fig)

def main():

    def devices_func(acc, i):
        if i % 2 == 0:
            acc.append(acc[i-1] * 2)
        else:
            acc.append(acc[i-1] * 5)
        return acc

    ec2_flavors = ('m3.medium', 'm4.large', 'm4.4xlarge')
    req_period_list = [3600] # , 8* 3600, 24 * 3600]
    #[10, 50, 100, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1000000, 5000000, 10000000]
    num_devices_list = reduce(devices_func, range(1,13), [10])
    num_devices_list = list(range(200000,10000000,100000))
    resolution = 60 * 5 # in seconds
    interval_duration = 30 * 24 * 3600 # one month in seconds
    lambda_memory = 128
    lambda_request_duration_ms = 200
    ec2_instances = [awscosts.EC2(flavor, MB_per_req=lambda_memory, ms_per_req=lambda_request_duration_ms) for flavor in ec2_flavors]

    for req_period in req_period_list:
        costs = []
        for num_devices in num_devices_list:
            lambda_instance = awscosts.Lambda(lambda_memory, lambda_request_duration_ms)
            time_serie = generate_requests_time_serie(num_devices, req_period, interval_duration, resolution)
            cost = aggregate_costs(req_period, resolution, interval_duration, num_devices, lambda_instance, ec2_instances, time_serie)

            print(cost['hits'], cost['reqs_per_second'], cost['lambda'], cost['ec2_m3.medium_cost'] * cost[f'ec2_m3.medium_instances'], cost['ec2_m4.large_cost'] * cost[f'ec2_m4.large_instances'], cost['ec2_m4.4xlarge_cost']*cost[f'ec2_m4.4xlarge_instances'])

            costs.append(cost)

        draw_costs_by_num_devices(costs, num_devices_list, ec2_flavors, req_period)

if __name__ == "__main__":
    main()
