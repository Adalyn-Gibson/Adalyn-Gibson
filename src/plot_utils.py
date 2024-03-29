import numpy as np
from pylab import cm
import matplotlib
import matplotlib.pyplot as plt

__all__ = ['load_inferno', 'make_onerow']

def load_inferno(n=10, colormap='inferno'):
    """ Returns a discrete colormap with n values.
    """
    cmap = cm.get_cmap(colormap, n)
    colors = []
    for i in range(cmap.N):
        rgb = cmap(i)[:3]
        colors.append(matplotlib.colors.rgb2hex(rgb))
    colors = np.array(colors)[1:-1]
    return colors

def make_onerow():
    """
    Creates a broken axis plot for one visit.
    """
    fig, axes = plt.subplots(ncols=5, nrows=1,
                             figsize=(20,5))

    ax = axes.reshape(-1)

    d = 0.025

    for j in range(5):
        if j > 0 and j < 4:
            ax[j].spines['right'].set_visible(False)
            ax[j].spines['left'].set_visible(False)
            ax[j].set_yticks([])


            kwargs = dict(transform=ax[j].transAxes, color='k', clip_on=False)
            ax[j].plot((1-d,1+d), (-d,+d), **kwargs)
            ax[j].plot((1-d,1+d),(1-d,1+d), **kwargs)
            kwargs.update(transform=ax[j].transAxes)  # switch to the bottom axes
            ax[j].plot((-d,+d), (1-d,1+d), **kwargs)
            ax[j].plot((-d,+d), (-d,+d), **kwargs)

        elif j == 0:
            ax[j].spines['right'].set_visible(False)
            kwargs = dict(transform=ax[j].transAxes, color='k', clip_on=False)
            ax[j].plot((1-d,1+d), (-d,+d), **kwargs)
            ax[j].plot((1-d,1+d),(1-d,1+d), **kwargs)

        else:
            ax[j].spines['left'].set_visible(False)
            ax[j].set_yticks([])
            kwargs.update(transform=ax[j].transAxes)  # switch to the bottom axes
            ax[j].plot((-d,+d), (1-d,1+d), **kwargs)
            ax[j].plot((-d,+d), (-d,+d), **kwargs)

        ax[j].set_rasterized(True)

    return fig, ax


def make_tworow():
    """
    Creates a broken axis plot for one visit.
    """
    fig, axes = plt.subplots(ncols=5, nrows=2,
                             figsize=(20,10))

    ax = axes.reshape(-1)

    d = 0.025

    for j in range(len(ax)):

        if j!=0 and j !=4 and j!=5 and j !=9:
            ax[j].spines['right'].set_visible(False)
            ax[j].spines['left'].set_visible(False)
            ax[j].set_yticks([])


            kwargs = dict(transform=ax[j].transAxes, color='k', clip_on=False)
            ax[j].plot((1-d,1+d), (-d,+d), **kwargs)
            ax[j].plot((1-d,1+d),(1-d,1+d), **kwargs)
            kwargs.update(transform=ax[j].transAxes)

            ax[j].plot((-d,+d), (1-d,1+d), **kwargs)
            ax[j].plot((-d,+d), (-d,+d), **kwargs)

        elif j == 0 or j == 5:
            ax[j].spines['right'].set_visible(False)
            kwargs = dict(transform=ax[j].transAxes, color='k', clip_on=False)
            ax[j].plot((1-d,1+d), (-d,+d), **kwargs)
            ax[j].plot((1-d,1+d),(1-d,1+d), **kwargs)

        else:
            ax[j].spines['left'].set_visible(False)
            ax[j].set_yticks([])
            kwargs.update(transform=ax[j].transAxes)

            ax[j].plot((-d,+d), (1-d,1+d), **kwargs)
            ax[j].plot((-d,+d), (-d,+d), **kwargs)

        ax[j].set_rasterized(True)

    return fig, ax

def plot_binned_resid(x, yin, yoot, velbins, ebar_dict, ax1, ax2, factor,
                      color='k', markerfacecolor='w'):
    """
    Plots the binned residuals.
    """
    for i in range(len(velbins)-1):
        inds = ( (x >= velbins[i]) & (x < velbins[i+1]))

        ax1.errorbar((velbins[i]+velbins[i+1])/2.0,
                    np.nanmean(yin[inds] - yoot[inds])*factor,
                    yerr=np.nanstd(yin[inds] - yoot[inds])*factor, color=color,
                    markerfacecolor=markerfacecolor, **ebar_dict)

        ax2.errorbar((velbins[i]+velbins[i+1])/2.0,
                    np.nanmean(yin[inds] / yoot[inds]),
                    yerr=np.nanstd(yin[inds] / yoot[inds]), color=color,
                    markerfacecolor=markerfacecolor, **ebar_dict)
    return

def plot_combined_lines(table, lines, visit=1, factor=1e14, binned_resid=False,
                        nbins=20):
    """
    Creates an n x 3 grid of subplots comparing the combined line profiles,
    the difference between in- and out-of transit observations, and the ratio
    between in- and out-of transit observations (following the figures of Linsky
    et al. 2010).

    Parameters
    ----------
    table : astropy.table.Table
       Table outputs from `TransitsWithCos.combine_lines()`.
    lines : np.ndarray, list
       List of which lines were used in the analysis. This will be used as the
       subplot titles as well.
    """
    if type(visit) == list or type(visit) == np.ndarray:
        pass
    else:
        visit = [visit]

#    if len(lines)==1:
#        ncols=1
    #else:
    ncols=len(lines)+1

    fig, axes = plt.subplots(nrows=3, ncols=ncols, figsize=(24,10),
                             sharex=True)

    axes = axes.reshape(-1)
    fig.set_facecolor('w')

    color = ['k', 'r']
    color  = [['#590d22', '#003366', '#668151'],
              ['#ff758f', '#66b2ff', '#a0db72']]
    key = ['it', 'oot']

    velbins = np.linspace(table['velocity'].min(), table['velocity'].max(),
                          nbins)

    ebar_dict = {'marker':'o', 'zorder':10,
                 'ms':6, 'lw':1.5, 'markeredgewidth':1.5}
    x = (table['velocity'][1:] + table['velocity'][:-1])/2.0

    # dealing with table related things
    table = table[:-1]
    fcolname = 'line{0:02d}_{1}_flux_visit{2}'
    ecolname = 'line{0:02d}_{1}_error_visit{2}'
    it_colname = 'line{0:02d}_it_flux_visit{1}'
    oot_colname = 'line{0:02d}_oot_flux_visit{1}'

    offset = 0

    for k in range(len(visit)):

        for i in range(len(lines)):
            axes[i].set_title(lines[i])

            for j in range(2):

                y = table[fcolname.format(i, key[j], visit[k])]*factor
                yerr = table[ecolname.format(i, key[j], visit[k])]*factor

                if j == 1:
                    label='Visit {}'.format(visit[k]+1)
                else:
                    label = ''

                axes[i].plot(x, y+offset, color=color[j][int(visit[k])],
                             label=label)

                axes[i].fill_between(x, y-yerr+offset, y+yerr+offset,
                                     color=color[j][int(visit[k])], alpha=0.4,
                                     lw=0)

            if binned_resid:
                plot_binned_resid(x,
                                  table[it_colname.format(i, visit[k])],
                                  table[oot_colname.format(i, visit[k])],
                                  velbins, ebar_dict, axes[i+len(lines)+1],
                                  axes[i+(len(lines)+1)*2], factor,
                                  color[0][int(visit[k])],
                                  color[1][int(visit[k])])
                alpha = 0.5
            else:
                alpha = 1.0


            axes[i+len(lines)+1].plot(x,
                                      (table[it_colname.format(i, visit[k])] -
                                        table[oot_colname.format(i, visit[k])])*factor,
                                    color=color[1][int(visit[k])], alpha=alpha)


            axes[i+len(lines)*2+2].plot(x,
                                       (table[it_colname.format(i, visit[k])] /
                                         table[oot_colname.format(i, visit[k])]),
                                      color=color[1][int(visit[k])], alpha=alpha)

            if i == 0 and k == 0:
                summed_it = table[it_colname.format(i, visit[k])]
                summed_oot = table[oot_colname.format(i, visit[k])]
            else:
                summed_it += table[it_colname.format(i, visit[k])]
                summed_oot += table[oot_colname.format(i, visit[k])]

        offset += 0.6

    axes[len(lines)].plot(x, summed_it*factor, c='k', label='Transit')
    axes[len(lines)].plot(x, summed_oot*factor, c='r', label='Non-transit')
    axes[len(lines)].legend(fontsize=14)


    axes[len(lines)*2+1].plot(x,
                              (summed_it - summed_oot)*factor,
                              'k', alpha=alpha)
    axes[len(lines)*3+2].plot(x, summed_it / summed_oot, 'k',
                              alpha=alpha)

    ebar_dict['ms'] = 8
    if binned_resid:
        plot_binned_resid(x,
                          summed_it,
                          summed_oot,
                          velbins, ebar_dict, axes[len(lines)*2+1],
                          axes[len(lines)*3+2], factor)


    axes[len(lines)].set_title('Combined')

    axes[0].set_ylabel('Flux Density\n[10$^{-14}$ erg s$^{-1}$ cm$^{-1} \AA^{-1}$]')
    axes[len(lines)+1].set_ylabel('Difference\n(In - Out)')
    axes[(len(lines)+1)*2].set_ylabel('Ratio\n(In/Out)')

    leg = axes[0].legend()
    for legobj in leg.legendHandles:
        legobj.set_linewidth(4.0)

    for i in np.arange((len(lines)+1),(len(lines)+1)*2,1):
        print(i)
        axes[i].axhline(0, color='darkorange')
        axes[i+len(lines)+1].axhline(1, color='darkorange')
        div = table[it_colname.format(0, visit[k])]/table[oot_colname.format(0, visit[k])]
        if np.nanmax(np.abs(div)) > 3 and i < (len(lines)+len(lines)+1):
            axes[i+len(lines)+1].set_ylim(-0.5,3)

        if np.nanmax(np.abs(summed_it/summed_oot)) > 3:
            print('bad')
            axes[-1].set_ylim(-1,3)

    axes[-2].set_xlabel(r'Velocity [km s$^{-1}$]')
    axes[-1].set_xlabel(r'Velocity [km s$^{-1}$]')
    return fig
