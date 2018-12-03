import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error, precision_recall_curve, average_precision_score

import scipy.stats as st

import statsmodels.api as sm
## This is a temp fix for statsmodes setting breaking pickling ##
## https://github.com/statsmodels/statsmodels/issues/4772 ##
import types, pickle
if types.MethodType in pickle.dispatch_table.keys():
    del pickle.dispatch_table[types.MethodType]

import matplotlib.pyplot as plt
import seaborn as sns

import vogel.preprocessing as v_prep
import vogel.utils as v_utils

### Model Statistics

def weighted_gini(weight, actual, predicted):
    # Sort by predicted in descending order
    sort_index = np.argsort(predicted)[::-1]
    weight = weight[sort_index]
    actual = actual[sort_index]
    # Cumulative sums
    cumulative_weight = np.cumsum(weight)
    cumulative_actual = np.cumsum(weight * actual)
    # Calculate products
    sum_a = sum(cumulative_weight[1:] * cumulative_actual[:-1])
    sum_b = sum(cumulative_weight[:-1] * cumulative_actual[1:])
    # Rescale
    gini = (sum_b - sum_a) / (cumulative_weight[-1] * cumulative_actual[-1])
    return abs(gini)


def weighted_rmse(weight, actual, predicted):
    return np.sqrt(
        np.sum(weight * np.power(actual - predicted, 2)) / np.sum(weight))


def pearson_chi_sq_scale_estimate(actual,
                                  weight,
                                  predicted,
                                  p=100,
                                  tweedie_power=1.5):
    predicted_temp = predicted.copy()
    predicted_temp[predicted_temp <= 0] = .0000001

    n = len(actual)
    se = np.power(actual - predicted_temp, 2)  # square error
    v = np.power(predicted_temp, tweedie_power)  # variance function
    return 1 / (n - p) * np.sum(weight * se / v)


def weighted_average(x, w):
    "Returns the weighted average"
    return np.sum(x * w) / np.sum(w)


def chi_sq_tweedie(phi, p):
    "Standardizes groups of observations coming from tweedie distribution"

    def weighted_average(x, w):
        "Returns the weighted average"
        return np.sum(x * w) / np.sum(w)

    def inner(grp):
        wavg_actual = weighted_average(grp.actual, grp.weight)
        wavg_predicted = weighted_average(grp.predicted, grp.weight)
        return np.power(wavg_actual - wavg_predicted, 2) / (
            (phi * np.power(wavg_predicted, p)) / np.sum(grp.weight))

    return inner


def hl_tweedie_df(weight, actual, predicted, bins=10, phi=1.0, p=1.5):
    "Calculates Hosmer-Lemeshow statistic for observations coming from tweedie distribution"
    predicted_temp = predicted.copy()
    predicted_temp[predicted_temp <= 0] = .0000001

    qs = sm.stats.DescrStatsW(
        predicted, weights=weight).quantile(np.arange(1, bins) * 1 / bins)
    quantile = np.searchsorted(qs, predicted)
    df = pd.DataFrame({
        'weight': np.array(weight),
        'actual': np.array(actual),
        'predicted': np.array(predicted_temp),
        'quantile': np.array(quantile)
    })
    return df


def hl_tweedie(weight, actual, predicted, bins=10, phi=1.0, p=1.5):
    df = hl_tweedie_df(weight, actual, predicted, bins, phi, p)
    return df.groupby('quantile').apply(chi_sq_tweedie(phi, p)).sum()


def deviance_tweedie(actual, predicted, weight, p=1.5):
    predicted_temp = predicted.copy()
    predicted_temp[predicted_temp <= 0] = .0000001
    tweedie = sm.families.Tweedie(var_power=p)
    return tweedie.deviance(actual, predicted_temp, freq_weights=weight)


def model_stats_reg(
        train_set,
        valid_set
    ):
    """
    Returns common metrics for a regression model.
    
    Arrgs:
    
    train_set:
        dict: {'y' : list, 'pred' : list, 'w' : list}
    valid_set:
        dict: {'y' : list, 'pred' : list, 'w' : list}
    """
    out_dict = {'train': {}, 'valid': {}}
    has_weight = False
    if 'w' not in train_set:
        has_weight = True
        train_set['w'] = np.ones(len(train_set['y']))
        if valid_set is not None:
            train_set['w'] = np.ones(len(valid_set['y']))

    try:
        # The mean squared error
        out_dict['train']['rmse'] = [
            np.sqrt(mean_squared_error(train_set['y'], train_set['pred']))
        ]
        

        # The mean squared error
        out_dict['train']['mae'] = [mean_absolute_error(train_set['y'], train_set['pred'])]

        # Explained variance score: 1 is perfect prediction
        #     out_dict['train']['r2'] = [r2_score(train_y, train_pred)]
        

        # Gini
        out_dict['train']['gini'] = [
            weighted_gini(np.array(train_set['w']), np.array(train_set['y']), train_set['pred'])
        ]
        

        # weighted_rmse
        if has_weight:
            out_dict['train']['weighted_rmse'] = [
                weighted_rmse(np.array(train_set['w']), np.array(train_set['y']), train_set['pred'])
            ]
        

        if valid_set is not None:
            out_dict['valid']['rmse'] = [
                np.sqrt(mean_squared_error(valid_set['y'], valid_set['pred']))
            ]
            out_dict['valid']['mae'] = [mean_absolute_error(valid_set['y'], valid_set['pred'])]
            out_dict['valid']['gini'] = [
                weighted_gini(np.array(valid_set['w']), np.array(valid_set['y']), valid_set['pred'])
            ]
            out_dict['valid']['weighted_rmse'] = [
                weighted_rmse(np.array(valid_set['w']), np.array(valid_set['y']), valid_set['pred'])
            ]
            #     out_dict['valid']['r2'] = [r2_score(valid_y, valid_pred)]

    except Exception as e:
        print('Stats Failed to run')
        print(e)

    return out_dict


def model_stats_tweedie(train_set,
                        valid_set=None,
                        p=1.5):
    """
    Returns common metrics for a regression model 
    with a tweedie distribution assumptions.
    
    Arrgs:
    
    train_set:
        dict: {'y' : list, 'pred' : list, 'w' : list}
    valid_set:
        dict: {'y' : list, 'pred' : list, 'w' : list}
    p: (1.5)
        float: tweedie power. 
    """

    out_dict = model_stats_reg(
        train_set,
        valid_set
        )
    if 'w' not in train_set:
        train_set['w'] = np.ones(len(train_set['y']))
        if valid_set is not None:
            train_set['w'] = np.ones(len(valid_set['y']))

    # Tweedie Deviance
    out_dict['train']['tweedie_deviance'] = [
        deviance_tweedie(train_set['y'], train_set['pred'], train_set['w'], p=p)
    ]
    

    train_phi = 6000
    valid_phi = 6000  # TODO: pull from statsmodel

    out_dict['train']['hl_tweedie'] = [
        hl_tweedie(
        train_set['w'], train_set['y'], train_set['pred'], phi=train_phi, p=p)
    ]

    if valid_set is not None:
        out_dict['valid']['tweedie_deviance'] = [
            deviance_tweedie(valid_set['y'], valid_set['pred'], valid_set['w'], p=p)
        ]
        out_dict['valid']['hl_tweedie'] = [
            hl_tweedie(
            valid_set['w'], valid_set['y'], valid_set['pred'], phi=valid_phi, p=p)
        ]

    return out_dict


### Model Plots ###


def plot_xgb_fit(results, error='rmse', plt_size=(5.0, 5.0)):
    """
    Itteration fit plot for XGBoost
    
    Args:
    
    results:
        XGBoost Results:
    error: ('rmse')
        string: validation error type given to the model.
    plt_size: (5.0, 5.0)
        tuple: (width, height)
    """
    plt.rcParams['figure.figsize'] = plt_size

    epochs = len(results['validation_0'][error])
    x_axis = range(0, epochs)
    # plot log loss
    fig, ax = plt.subplots()
    ax.plot(x_axis, results['validation_0'][error], label='Train')
    if 'validation_1' in results:
        ax.plot(x_axis, results['validation_1'][error], label='Valid')
    ax.legend()
    plt.ylabel(error)
    plt.title('XGBoost Loss')
    plt.show()

    fig, ax = plt.subplots()
    ax.plot(x_axis, results['validation_0'][error], label='Train')
    ax.legend()
    plt.ylabel(error)
    plt.title('XGBoost Loss')
    plt.show()
    if 'validation_1' in results:
        fig, ax = plt.subplots()
        ax.plot(x_axis, results['validation_1'][error], label='Valid')
        ax.legend()
        plt.ylabel(error)
        plt.title('XGBoost Loss')
        plt.show()


def plot_hl(weight,
            actual,
            predicted,
            bins=10,
            phi=1.0,
            p=1.5,
            plt_size=(10, 5)):
    """
    Hosmer-Lemshow Plot
    
    Args:
    
    weight:
        list: model weights
    actual: 
        list: target values
    perdicted: 
        list: predicted values
    bins: (10)
        int: number of bins to display
    phi: (1.0)
        float: 
    p: (1.5)
        float: tweedie power
    plt_size: (5.0, 5.0)
        tuple: (width, height)
    """

    plt.rcParams['figure.figsize'] = plt_size

    hl_df = hl_tweedie_df(weight, actual, predicted, bins, phi, p)
    hl_df = hl_df.apply(pd.to_numeric)
    hl_df_qrt_actual = hl_df.groupby('quantile').apply(
        lambda x: weighted_average(x['actual'], x['weight'])).reset_index()
    hl_df_qrt_actual.columns = ['quantile', 'actual']
    hl_df_qrt_predicted = hl_df.groupby('quantile').apply(
        lambda x: weighted_average(x['predicted'], x['weight'])).reset_index()
    hl_df_qrt_predicted.columns = ['quantile', 'predicted']
    hl_df_qrt = pd.merge(hl_df_qrt_actual, hl_df_qrt_predicted, on='quantile')
    hl_df_qrt.plot(x='quantile')
    plt.show()


def plot_recall(actual, prediction, plt_size=(7, 7)):
    """
    Precision-Recall plot for Bimodal targets.
    
    Args:
    
    actual: 
        list: target values
    perdicted: 
        list: predicted values
    plt_size: (7.0, 7.0)
        tuple: (width, height)
    """
    plt.rcParams['figure.figsize'] = plt_size

    average_precision = average_precision_score(actual, prediction)

    precision, recall, _ = precision_recall_curve(actual, prediction)

    plt.step(recall, precision, color='b', alpha=0.2, where='post')
    plt.fill_between(recall, precision, step='post', alpha=0.2, color='b')

    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.ylim([0.0, 1.05])
    plt.xlim([0.0, 1.0])
    plt.title('2-class Precision-Recall curve: AP={0:0.2f}'.format(
        average_precision))

    plt.show()


def plot_compare_stats(metrics_summary, valid_only=True, plt_size=(10, 5)):
    """
    Given a metrics summary, scales and plots them.
    
    Args:
    
    metrics_summary: 
        pandas.DataFrame: model metric summary (model_stats_*)
    valid_only: (True)
        bool: plot only the validation data
    plt_size: (10.0, 5.0)
        tuple: (width, height)
    """
    plt.rcParams['figure.figsize'] = plt_size
    non_metrics = ['model_name', 'model_dict', 'set']
    metrics = np.setdiff1d(metrics_summary.columns, non_metrics).tolist()

    if valid_only:
        metrics_summary = metrics_summary[metrics_summary['set'] == 'valid']

    pipeline = v_prep.FeatureUnion([
        ('numeric',
         v_utils.make_pipeline(
             v_prep.ColumnExtractor(None, None, want_numeric=True),
             v_prep.MinMaxScaler())),
        ('cats',
         v_utils.make_pipeline(
             v_prep.ColumnExtractor(None, None, want_numeric=False))),
    ])

    metrics_summary = pipeline.fit_transform(metrics_summary)

    fig, ax = plt.subplots()
    for metric in metrics:
        ax.plot(
            metrics_summary['model_name'],
            metrics_summary[metric],
            label=metric)
    ax.legend()

    plt.xticks(rotation=90)
    plt.show()


def plot_pareto(y,
                x,
                numeric=False,
                sort_values=False,
                cutoff=.95,
                plt_size=(15, 5)):
    """
    Pareto Plot.
    
    y: 
        list: values for y axis
    x:
        list: labels for x axis
    numeric: (False)
        bool: Treat catigories as numeric (numeric sort & spacing)
    sort_values: (False)
        bool: sort by value counts
    cutoff: (.95)
        float: cut off line point for plot
    plt_size: (10.0, 5.0)
        tuple: (width, height)
    """

    plt.rcParams['figure.figsize'] = plt_size

    temp_df = pd.DataFrame({'data': y})
    # temp_df.index = temp_index
    temp_df['label'] = x

    if sort_values:
        temp_df = temp_df.sort_values('data')

    # optional sort by value
    temp_df['per_ttl'] = temp_df['data'].cumsum() / temp_df['data'].sum()

    if not numeric:
        temp_df['label'] = temp_df['label'].astype('str')

    max_per = temp_df['per_ttl'][temp_df['per_ttl'] < cutoff].max()

    fig, ax = plt.subplots()
    ax2 = ax.twinx()

    ax.bar(temp_df['label'], temp_df['data'])
    ax2.plot(list(temp_df['label']), temp_df['per_ttl'], ls='--', c='red')
    #     ax2.axhline(.95, ls='--', c='red')
    plt.axvline(
        temp_df['label'][temp_df['per_ttl'] == max_per].values[0],
        ls='--',
        c='red')
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=90)

    plt.show()


### One way GLM Plots ###
"""
This chunk of code is made to use with statsmodels GLMs. 
It will show how individual features fit to a model.
"""


def get_glm_label_and_count_table(label_dicts, data):
    """
    get labels and counts for binned GLM models.
    Used in train.py create_feature_stats_table.
    
    Arrgs:
    
    label_dicts:
        dict: dict from utils.py get_label_dicts()
    data: 
        list: feature data
    """
    out_df = pd.DataFrame()

    def get_label_counts(bins_df, feature, data):
        temp = pd.DataFrame(data[list(
            bins_df.index[bins_df['hold'] != 1])].sum())
        temp.columns = ['count']
        #cal holdout count
        temp = pd.concat([
            temp,
            pd.DataFrame(
                {
                    'count': [len(data) - temp['count'].sum()]
                },
                index=[feature + '___const'])
        ])

        return temp

    for feature_set in label_dicts.items():
        feature_name = feature_set[0]
        feature_dict = feature_set[1]
        items = feature_dict['items']
        bins_df = pd.concat([
            pd.DataFrame({
                'bin': items,
                'hold': np.zeros(len(items)),
                'sep' : feature_dict['sep']
            }),
            pd.DataFrame({
                'bin': [str(feature_dict['hold'])],
                'hold': [1],
                'sep' : feature_dict['sep']
            })
        ])

        bins_df.index = bins_df.apply(lambda x: v_utils.label_dict_formater(
                                                 x['sep'], 
                                                 feature_name, 
                                                 str(x['bin'])), axis=1)
        bins_df.index = np.where(bins_df['hold'] == 1, feature_name + '___const', bins_df.index)

        bins_df = pd.concat(
            [bins_df, get_label_counts(bins_df, feature_name, data)], axis=1)
        out_df = pd.concat([out_df, bins_df])

    out_df['bin'] = out_df['bin'].astype('str')
    return out_df


def get_glm_error(mdl_stats, label_dicts):
    """
    calculate error for GLM model fit_transform
    
    Arrgs:
    
    mdl_stats:
        pandas.DataFrame: 
    label_dicts:
        dict: dict from utils.py get_label_dicts()
    """
    out_df = pd.DataFrame()

    base_coef = mdl_stats['Coef.'][mdl_stats.index == 'const'].values[0]
    base_std = mdl_stats['Std.Err.'][mdl_stats.index == 'const'].values[0]
    base_cov = mdl_stats['cov'][mdl_stats.index == 'const'].values[0]

    def calc_err(row, err_type):
        coefs = base_coef + row['Coef.']
        err_term = 2 * np.sqrt(base_std**2 + row['Std.Err.']**2 +
                               2 * row['cov'])
        if err_type == 'pos':
            return np.exp(coefs + err_term)
        elif err_type == 'neg':
            return np.exp(coefs - err_term)

    for feature_set in label_dicts.items():
        feature_name = feature_set[0]
        feature_dict = feature_set[1]
        items = feature_dict['items']

        #filter data set to one feature group
        if feature_dict['sep'] != '()':
            mod_features = [feature_name + feature_dict['sep'] + str(x)
                            for x in items] + [feature_name + '___const']
        else:
            mod_features = [feature_name + ' (' + str(x) + ')'
                            for x in items] + [feature_name + '___const']
        mdl_stats_fltrd = mdl_stats[mdl_stats.index.isin(mod_features)].copy()

        #set stats for base level
        mdl_stats_fltrd['Coef.'] = np.where(
            mdl_stats_fltrd.index == feature_name + '___const', 0,
            mdl_stats_fltrd['Coef.'])
        mdl_stats_fltrd['Std.Err.'] = np.where(
            mdl_stats_fltrd.index == feature_name + '___const', base_std,
            mdl_stats_fltrd['Std.Err.'])
        mdl_stats_fltrd['cov'] = np.where(
            mdl_stats_fltrd.index == feature_name + '___const', base_std,
            mdl_stats_fltrd['cov'])

        # calc error
        mdl_stats_fltrd['error+'] = mdl_stats_fltrd.apply(
            lambda x: calc_err(x, 'pos'), axis=1)
        mdl_stats_fltrd['error-'] = mdl_stats_fltrd.apply(
            lambda x: calc_err(x, 'neg'), axis=1)

        #set error for base level
        mdl_stats_fltrd['error+'] = np.where(
            mdl_stats_fltrd.index == feature_name + '___const',
            np.exp(base_coef + base_std * 2), mdl_stats_fltrd['error+'])
        mdl_stats_fltrd['error-'] = np.where(
            mdl_stats_fltrd.index == feature_name + '___const',
            np.exp(base_coef - base_std * 2), mdl_stats_fltrd['error-'])

        mdl_stats_fltrd['coef_exp'] = np.exp(mdl_stats_fltrd['Coef.'] +
                                             base_coef)

        out_df = pd.concat([out_df, mdl_stats_fltrd])

    return out_df


def plot_glm_one_way_fit(bin_fit_stats,
                         plot_error=True,
                         round_at=2,
                         rotate_x=True,
                         predicted_value=True,
                         scale_to_zero=False,
                         base_line=True,
                         pad_bar_chart=True,
                         plt_size=(10, 5)):
    """
    one way feature fits for a GLM

    Args:
    
    bin_fit_stats: 
        Pandas.DataFrame: bin | count | coef_exp | error+ | error- | hold
    round_at: (2)
        int: rounding point
    predicted_value: (True)
        bool: plot predicted value or liniear prodictor
    rotate_x: (True)
        bool: rotate x axis lables
    scale_to_zero: (False)
        bool: scale all valuse where the base is 0
    base_line: (True)
        bool: draw line at base level on y axis
    pad_bar_chart: (False)
        bool: add 100% padding to the top of x axis for the bar chart
    plt_size: (10, 5)
        tuple: (width, height)
    """
    plt.rcParams['figure.figsize'] = plt_size

    def is_number(s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    temp_df = bin_fit_stats.copy()

    if temp_df['bin'].apply(lambda x: is_number(x)).all():
        temp_df['bin'] = temp_df['bin'].astype('float')
        temp_df = temp_df.sort_values('bin')
        temp_df['bin'] = round(temp_df['bin'], round_at).astype('str')
    else:
        temp_df = temp_df.sort_values('count', ascending=False)

    if not predicted_value:
        temp_df['coef_exp'] = np.log(temp_df['coef_exp'])
        temp_df['error+'] = np.log(temp_df['error+'])
        temp_df['error-'] = np.log(temp_df['error-'])

    if scale_to_zero:
        base_coef = temp_df['coef_exp'][temp_df['hold'] == 1].values[0]
        temp_df['error+'] = temp_df['error+'] - base_coef
        temp_df['error-'] = temp_df['error-'] - base_coef
        temp_df['coef_exp'] = temp_df['coef_exp'] - base_coef

    index = temp_df['bin']

    fig, ax = plt.subplots()
    ax2 = ax.twinx()

    ax.bar(
        index, temp_df['count'], width=.8, color='yellow', edgecolor='black')
    ax2.plot(index, temp_df['coef_exp'], ls='-', c='#006400', marker='x')

    if plot_error:
        ax2.fill_between(
            index,
            temp_df['error+'],
            temp_df['error-'],
            alpha=.2,
            edgecolor='gray',
            color='green')

    if rotate_x:
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=90)

    if base_line:
        plt.axhline(
            temp_df['coef_exp'][temp_df['hold'] == 1].values[0],
            ls='--',
            c='#006400')

    if pad_bar_chart:
        ax.set_ylim([0, temp_df['count'].max() * 2])

    ax2.tick_params(axis='y', colors='#006400')
    ax2.spines['right'].set_color('#006400')
    ax.spines['right'].set_color('#006400')

    plt.show()

### END: One way GLM Plots ###

def plot_one_way_fit(feature,
                     perdiction,
                     target=None,
                     objective='mean',
                     error='perc',
                     target_error=False,
                     rotate_x=True,
                     pad_bar_chart=False,
                     plt_size=(10, 5)):
    """
    Create a bar & line plot to show a features relationship to the models outcome
    
    Args:
    
    feature:
        list: feature values
    perdiction: 
        list: prediction values
    target: (None)
        list: optional target values
    objective:
        string: objective to plot. ('mean', 'median')
    error: ('perc')
        string:
            'perc': Plot 25 and 75 percentiles
            'std': Plot Standard Error
    target_error: (False)
        bool: Plot Targets error
    rotate_x: (True)
        bool: rotate x axis lables
    pad_bar_chart: (False)
        bool: add 100% padding to the top of x axis for the bar chart
    plt_size: (10, 5)
        tuple: (width, height)
    """
    plt.rcParams['figure.figsize'] = plt_size

    def format_describe(data):
        temp = data.groupby(data.columns[0]).describe()
        temp.columns = temp.columns.droplevel()
        temp.columns = [('{0}_{1}').format(data.columns[1], x)
                        for x in temp.columns]
        return temp

    if objective == 'median':
        objective = '50%'

    temp = pd.concat([feature, perdiction], axis=1)
    temp.columns = ['feature', 'prediction']
    temp = format_describe(temp)

    if target is not None:
        temp_2 = pd.concat([feature, target], axis=1)
        temp_2.columns = ['feature', 'target']
        temp_2 = format_describe(temp_2)
        temp = pd.concat([temp, temp_2], axis=1)

    fig, ax = plt.subplots()
    ax2 = ax.twinx()

    if np.issubdtype(temp.index.dtype, np.number):
        index = [str(round(x, 2)) for x in temp.index]
    else:
        index = temp.index

    ax.bar(
        index,
        temp['prediction_count'],
        width=.8,
        color='yellow',
        edgecolor='black')
    if target is not None:
        ax2.plot(
            index,
            temp['target_' + objective],
            ls='--',
            c='orange',
            marker='o')
    ax2.plot(
        index, temp['prediction_' + objective], ls='-', c='green', marker='x')

    if error == 'perc':
        ax2.fill_between(
            index,
            temp['prediction_75%'],
            temp['prediction_25%'],
            alpha=.3,
            edgecolor='black',
            color='green',
            label='Prediction 25-75%')
        if (target is not None) & (target_error == True):
            ax2.fill_between(
                index,
                temp['target_75%'],
                temp['target_25%'],
                alpha=.3,
                edgecolor='black',
                color='orange',
                label='Target 25-75%')
    elif error == 'std':
        ax2.fill_between(
            index,
            temp['prediction_' + objective] + (temp['prediction_std'] * 1.96),
            temp['prediction_' + objective] - (temp['prediction_std'] * 1.96),
            alpha=.3,
            edgecolor='black',
            color='green',
            label='Prediction Error')
        if (target is not None) & (target_error == True):
            ax2.fill_between(
                index,
                temp['target_' + objective] + (temp['target_std'] * 1.96),
                temp['target_' + objective] - (temp['target_std'] * 1.96),
                alpha=.3,
                edgecolor='black',
                color='orange',
                label='Target Error')

    if rotate_x:
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=90)

    if pad_bar_chart:
        ax.set_ylim([0, temp['prediction_count'].max() * 2])

    ax2.legend()
    plt.show()
