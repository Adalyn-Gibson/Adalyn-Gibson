import os, sys
import numpy as np
from astropy import units
from astropy.io import fits
from astropy import constants
from lmfit.models import Model
import matplotlib.pyplot as plt
from scipy.signal import gaussian
from scipy.signal import find_peaks
from scipy.optimize import minimize
from scipy.interpolate import interp1d
from astropy.table import Table, Column
from lightkurve.lightcurve import LightCurve

import model_utils
import spectral_utils

__all__ = ['FlaresWithCOS']

class FlaresWithCOS(object):
    """
    A class to analyze flares as observed with Hubble/COS.
    """
    def __init__(self, wavelength, flux, flux_err, time,
                 orbit, time_unit=units.s):
        """
        Initializes the class.

        Parameters
        ----------
        wavelength : np.ndarray
           An array of wavelengths. Should be the same shape
           as the flux and flux_err arrays.
        flux : np.ndarray
           An array of flux spectra. Should be the same shape
           as the wavelength and flux_err arrays.
        flux_err : np.ndarray
           An array of errors on each flux point. Should be
           the same shape as the wavelength and flux arrays.
        time : np.array
           An array of times per each spectra. Should be the
           same length as the wavelength, flux, and flux_err
           arrays.
        orbit : np.array
           An array of which orbit each specta was observed
           in.
        time_unit : astropy.units.Unit
           The units of the time array. Default is seconds.
        """

        self.wavelength = wavelength+0.0
        self.flux = flux + 0.0
        self.flux_err = flux_err+0.0
        self.time = time * time_unit
        self.orbit = orbit
        self.line_table = None
        self.lsf_table = None
        self.width_table = Table()
        self.error_table = Table()
        self.fuv130 = None
        self.continuum_mask = None

        self.flux_units =  units.erg / units.s / units.cm**2 / units.AA


    def load_line_table(self, path, fname='line_table.txt',
                        format='csv', comment='#'):
        """
        Loads in a table of lines. Table is organized
        as ion, central wavelength (AA),
        the minimum velocity of the line (vmin; km/s),
        and
        the maximum velocity of the line (vmax; km/s).

        Parameters
        ----------
        path : str
           Where the line table is stored.
        fname : str, optional
           The name of the line table. Default is
           `line_table.txt`.
        format : str, optional
           The format the table is stored in. Default
           is `csv`.
        comment : str, optional
           If comments are present in the table, provide the
           string identifier. Default is `#`.

        Attributes
        ----------
        line_table : astropy.table.Table
        """
        self.line_table = Table.read(os.path.join(path, fname),
                                     format=format,
                                     comment=comment)


    def to_velocity(self, wave, mid=None):
        """
        Converts wavelength to velocity space given some
        reference wavelength.

        Parameters
        ----------
        wave : np.array
           Wavelength array
        mid : float, optional
           The middle wavelength to center 0 km/s on.
           Default is none and will take the center of
           the spectrum as the 0 point.

        Returns
        -------
        rv_km_s : np.array
           The velocity in km/s.
        mid : float
           Where the velocity = 0.
        """
        rv_km_s, mid = spectral_utils.to_velocity(wave, mid)
        return rv_km_s, mid


    def measure_ew(self, ion=None, line=None, vmin=None,
                   vmax=None, orbit='all', binsize=3):
        """
        Measures the equivalent width of a given line. Either the
        ion name (from self.line_table) can be passed in or the
        center wavelength, vmin (minimum velocity of the line), and
        the vmax (maximum velocity of the line) can be passed in.

        Parameters
        ----------
        ion : str, optional
           The ion name in self.line_table to use
           for the analysis.
        line : float, optional
           The center of the line to measure.
        vmin : float, optional
           The lower velocity to incorporate into the
           line measurement.
        vmax : float, optional
           The upper velocity to incorporate into the
           line measurement.
        orbit : int, optional
           Applies a mask to a specified orbit. Default
           is all orbits.
        binsize : int, optional
           Accounts for binning in the error calculation.
           If the data is not binned, use binsize=1. Default
           is 3.

        Attributes
        ----------
        width_table : astropy.table.Table
           Adds a column of measured equivalent widths to the
           attribute width_table. Columns are replaced when
           lines are re-measured.
        error_table : astropy.table.Table
           Adds a column of equivalent width errors to the
           attribute error_table. Columns are replaced when
           lines are re-measured.

        """
        wt, et = spectral_utils.measure_ew(self.orbit, self.time, self.wavelength,
                                           self.flux, self.flux_err,
                                           self.line_table, ion=ion,
                                           line=line, vmin=vmin, vmax=vmax,
                                           orbit_num=orbit, binsize=binsize,
                                           width_table=self.width_table,
                                           error_table=self.error_table)
        self.width_table = wt
        self.error_table = et


    def measure_FUV130(self):
        """
        Integrates the FUV130 flux, as defined in Parke Loyd et al. (2018).

        Attributes
        ----------
        fuv130 : np.ndarray
           Array of flux values that constitute the FUV130 band.
        """
        fuv130 = np.zeros(len(self.time.value))
        fuv130_err = np.zeros(len(self.time.value))

        for i in range(len(self.wavelength)):
            mask = np.where( ((self.wavelength[i] >= 1173.65) & (self.wavelength[i] <= 1197)) |
                             ((self.wavelength[i] >= 1230) & (self.wavelength[i] <= 1274.04)) |
                             ((self.wavelength[i] >= 1329.25) & (self.wavelength[i] <= 1355.49)) )[0]


            fuv130[i] = np.nansum(self.flux[i][mask])

            fuv130_err[i] = np.sqrt(np.nansum(self.flux_err[i][mask]**2) / len(mask))

        self.fuv130 = fuv130 * self.flux_units * units.AA
        self.fuv130_err = fuv130_err * self.flux_units * units.AA
        return mask


    def measure_flare_params(self, qmask, fmask, d, flux=None):
        """
        Measures the energy and equivalent duration of the flare.
        Flare parameter equations were taken from Loyd et al. 2018.

        Parameters
        ----------
        qmask : np.array
           Mask for the regions of the FUV130 that should be considered
           the quiescent flux.
        fmask : np.array
           Mask for the regions of the FUV130 that should be considered
           the flare.
        d : float
           The distance to the star with astropy.units.Unit quantity.
        flux : np.array, optional
           The flux array to measure the flare parameters. If None, this
           function uses the FUV130 flux.

        Returns
        -------
        energy : float
           The measured energy of the flare.
        ed : float
           The measured equivalent duration of the flare.
        """
        if flux is None:
            if self.fuv130 is None:
                self.measure_FUV130() * self.flux_units
            flux = self.fuv130 + 0.0
        if flux is not None:
            flux = flux * self.flux_units / units.AA

        Fq = np.nanmedian(flux[qmask]/10**-13) #* units.erg / units.s / units.cm**2
        Ff = (flux[fmask]/10**-13) #* units.erg / units.s / units.cm**2

        eng = np.trapz(Ff-Fq, x=self.time[fmask]) * 4 * np.pi * d**2
        dur = np.trapz((Ff-Fq)/Fq, x=self.time[fmask])
        return eng, dur

    def build_sed(self, d, mask=None):
        """
        Calculates the flux for given regions of the spectrum. This
        will loop through all spectra in `self.flux`.

        Parameters
        ----------
        d : astropy.units.Unit
           The distance to the star with the corresponding distance
           units.
        mask : np.array, optional
           A mask for what region to calculate the flux. Default is None.
           If the mask is None, it will calculate the flux in regions
           of the continuum.

        Returns
        ----------
        sed : np.ndarray
           An array of shape `self.flux` that has the calculated flux
           in regions applied by the input mask.
        """
        if mask is None:
            if self.continuum_mask is None:
                self.identify_continuum()
            mask = self.continuum_mask[0] == 0

        sed = np.zeros(len(self.flux))

        for i in range(len(self.flux)):
            eng = np.trapz(self.flux[i][mask]*self.flux_units,
                           x=self.wavelength[i][mask]*units.AA) * 4 * np.pi * d**2
            eng = eng.to(units.erg/units.s)
            sed[i] = eng.value

        return sed


    def fit_flare(self, ion, mask, model='white light',
                  amp=None, t0=None, decay=None, rise=None,
                  eta=None, omega=None, alpha=None, offset=None,
                  x=None, y=None, yerr=None):
        """
        Fits a flare model to the data. There are two model options available:
        1. Flare model from Davenport et al. (2016) : Gaussian rise + exponential
        decay. This model requires parameters: amp, t0, decay, rise.
        2. Skewed Gaussian distribution (this work). This model requires
        parameters: eta, omega, alpha.

        This function can fit multi-peaked flare events. Do this by setting
        the parameters to arrays of length N, where N is the number of flares
        you wish to fit.

        Parameters
        ----------
        ion : str
           The ion to fit the flare model to.
        mask : np.array
           A mask that isolates the flare in question. Should be
           of length `self.time`.
        model : str
           Model type you wish to fit. Default is 'white light'. Additional
           models include: 'skewed_gaussian' and 'convolved' (which is
           a convolution of the other two models).
        amp : np.array, optional
           A first guess at the amplitude of each flare for the flare
           model. Should be of length `nflares`.
           Default is None. If None, will take the maximum value
           in the flux array.
        t0: np.array, optional
           A first guess at the peak time of each flare for the flare
           model. Should be of length `nflares`. Default is None.
           If None, will take the time of maximum value in the flux
           array.
        decay : np.array, optional
           A first guess at the decay scaling factor for each flare.
           Should be of length `nflares`. Default is None. If None,
           will populate an array of values = 0.1.
        eta : np.array, optional
           A first guess at the peak time of the flare (i.e. the mean
           of the distribution). Default is None. If None, will take the
           time of maximum value in the flux array.
        omega : np.array, optional
           The scale of the Gaussian distribution. Default is None. If
           None, will scale to the maximum flux value in the array.
        alpha : np.array, optional
           Skewness of the distribution. Default is None. If None, will
           test skew values of alpha > 0.

        Returns
        -------
        best_fit : np.array
           The best fit values for the flare model. Returns array with
           t0, amp, and decay values.
        model : np.array
           The flare model derived from the best fit values. Will be of
           length = `flux`.
        """

        time = np.array(self.time[mask].value) + 0.0
        flux = np.array(self.width_table[ion][mask]) + 0.0
        flux_err = np.array(self.error_table[ion][mask]) /10.0 #+ 0.0

        #if x is not None and y is None:
        #    finterp = interp1d(time, flux)
        #    flux = finterp(x)

        #    einterp = interp1d(time, flux_err)
        #    flux_err = einterp(x)

        if x is not None:
            time = x + 0.0
        if y is not None:
            flux = y + 0.0
        if yerr is not None:
            flux_err = yerr + 0.0

        if offset is None:
            if model.lower() == 'white light':
                offset = np.full(len(amp), 0)
            else:
                offset = np.full(len(eta), 0)

        ##########
        ### WHITE LIGHT MODEL ###
        ##########
        if model.lower() == 'white light':

            fmodel = Model(model_utils.flare_model,
                           prefix='f{0:02d}_'.format(0))

            if len(amp) > 1:
                for i in range(1, len(amp)):
                    fmodel += Model(model_utils.flare_model,
                                    prefix='f{0:02d}_'.format(i))

            pars = fmodel.make_params()

            for i in range(len(amp)):
                pars['f{0:02d}_{1}'.format(i, 'amp')].set(value=amp[i], min=flux.min(), max=amp[i]*20)
                pars['f{0:02d}_{1}'.format(i, 't0')].set(value=t0[i], min=t0[i]-60, max=t0[i]+60)
                pars['f{0:02d}_{1}'.format(i, 'rise')].set(value=rise[i], min=0.001, max=100)
                pars['f{0:02d}_{1}'.format(i, 'decay')].set(value=decay[i], min=0.001, max=300)
                pars['f{0:02d}_offset_g'.format(i)].set(value=0, min=-1, max=10)
                pars['f{0:02d}_offset_e'.format(i)].set(value=0, min=-1, max=10)

        ##########
        ### SKEWED GAUSSIAN MODEL ###
        ##########
        elif model.lower() == 'skewed gaussian':

            fmodel = Model(model_utils.skewed_gaussian, prefix='f{0:02d}_'.format(0))

            if len(eta) > 1:
                for i in range(1, len(eta)):
                    fmodel += Model(model_utils.skewed_gaussian, prefix='f{0:02d}_'.format(i))

            pars = fmodel.make_params()

            for i in range(len(eta)):
                pars['f{0:02d}_{1}'.format(i, 'eta')].set(value=eta[i], min=eta[i]-100, max=eta[i]+100)
                pars['f{0:02d}_{1}'.format(i, 'omega')].set(value=omega[i], min=0.1, max=500)
                pars['f{0:02d}_{1}'.format(i, 'alpha')].set(value=alpha[i], min=0, max=200)
                pars['f{0:02d}_{1}'.format(i, 'normalization')].set(value=1e-3, min=1e-7, max=1)
                pars['f{0:02d}_{1}'.format(i, 'offset')].set(value=0, min=-1, max=10)


        ##########
        ### CONVOLVED MODELL ###
        ##########
        elif model.lower() == 'convolved':

            fmodel = Model(model_utils.convolved_model,
                           prefix='f{0:02d}_'.format(0))

            if len(eta) > 1:
                for i in range(1, len(eta)):

                    fmodel += Model(model_utils.convolved_model,
                                    prefix='f{0:02d}_'.format(i))

            pars = fmodel.make_params()

            for i in range(len(eta)):
                pars['f{0:02d}_{1}'.format(i, 'eta')].set(value=eta[i], min=eta[i]-100, max=eta[i]+100)
                pars['f{0:02d}_{1}'.format(i, 'omega')].set(value=omega[i], min=1, max=750)
                pars['f{0:02d}_{1}'.format(i, 'alpha')].set(value=alpha[i], min=0, max=200)
                pars['f{0:02d}_{1}'.format(i, 'normalization')].set(value=1, min=0.9, max=1.1)

                pars['f{0:02d}_{1}'.format(i, 'amp')].set(value=amp[i], min=flux.min(), max=amp[i]*20)
                pars['f{0:02d}_{1}'.format(i, 't0')].set(value=t0[i], min=np.nanmin(time), max=np.nanmax(time))
                pars['f{0:02d}_{1}'.format(i, 'rise')].set(value=rise[i], min=0.001, max=100)
                pars['f{0:02d}_{1}'.format(i, 'decay')].set(value=decay[i], min=0.001, max=300)

                pars['f{0:02d}_{1}'.format(i, 'offset')].set(value=0, min=-1, max=10)


        else:
            print('The input model is not implemented.')
            print('Available models: white light, skewed gaussian, convolved')
            return


        init = fmodel.eval(pars, x=time)

        out  = fmodel.fit(flux,
                          pars, x=time)

        return time, flux, flux_err, fmodel, init, out


    def load_lsf_model(self, fname):
        """
        Convolves the line spread function with a gaussian to
        fit line profiles.

        Parameters
        ----------
        fname : str
           The path + name of the line spread function file.

        Attributes
        ----------
        lsf_table : astropy.table.Table
           A table of convolved models. The models are created
           in steps of 5 Angstroms.
        """

        lsf = Table.read(fname, format='ascii')

        lsf_table = Table()

        for key in lsf.colnames:
            name = lsf[key][0]
            data = lsf[key][1:-1] # removes bad rows from the LSF
            lsf_table.add_column(Column(data, name))

        self.lsf_table = lsf_table


    def model_line_shape(self, ion, mask, shape='gaussian',
                         ext=100, ngauss=1, f=None, mus=None,
                         ferr=None, lsf=None, scaling=1e14):
        """
        Takes an ion from the line list and fits a convolved Gaussian
        with the line spread function. Line profiles are fit by conducting
        a chi-squared fit. The line profile is fit in velocity space.

        Parameters
        ----------
        ion : str
           The ion in the line list to fit a line to.
        mask : np.ndarray
           A mask for the out-of-flare observations to create a
           template from.
        shape : str, optional
           The profile shape to convolve with the line spread
           function. Default is `gaussian`.
        ext : float, optional
           Addition to the vmin and vmax of a given ion to ensure the
           line profile can be well fit to the data. Default = 100 [km/s].
        ngauss : int, optional
           The number of Gaussians used to fit the profile. Default is 1.
        x0 : np.ndarray, optional
           The list of initial guesses for each Gaussian model. x0 should
           be of shape (ngauss,4), where the 4 entries are:
           mu (mean), std (standard deviation), sf (Gaussian scaling factor),
           scale (additional scaling factor). Default is
           x0 = [0, 20, 14, 4].
        default_bounds : np.ndarray, optional
           The list of bounds to use in the scipy.optimize.minimize function.
           Can either give 1 set of bounds for mu, std, sf, and scale
           (len(default_bounds)==4) or bounds for each parameter passed in
           (len(default_bounds)==4*ngauss). Default is [(-100,100), (1,100),
           (1,3000), (1,20)].
           """
        def gaussian(x, mu, std, f):#, off):
            nonlocal lsf
            exp = -0.5 * (x-mu)**2 / std**2
            denom = std * np.sqrt(np.pi * 2.0)
            g = f / denom * np.exp(exp)
            if lsf is not None:
                return np.convolve(lsf, g, 'same')# + off
            else:
                return g

        wc   = self.line_table[self.line_table['ion']==ion]['wave_c'][0]
        vmin = self.line_table[self.line_table['ion']==ion]['vmin'][0]
        vmax = self.line_table[self.line_table['ion']==ion]['vmax'][0]

        velocity, _ = self.to_velocity(np.nanmedian(self.wavelength[mask],axis=0),wc)
        velocity    = velocity.value + 0.0

        reg = np.where( (velocity >= vmin-ext) & (velocity <= vmax+ext) )[0]

        wave = self.wavelength[mask][:,reg]

        # finds the line spread profile closest to the ion in question #
        if lsf is not None:

            argmin = np.argmin(np.abs([float(i) for i in self.lsf_table.colnames] - wc))
            lsf = self.lsf_table[self.lsf_table.colnames[argmin]].data
            lsf /= np.nanmax(lsf)

            # interpolate line spread function to same length as line profile #
            ivel = np.linspace(velocity[reg][0],
                               velocity[reg][-1],
                               len(lsf))
            lsf_interp = interp1d(ivel, lsf)
            lsf = lsf_interp(velocity[reg]) + 0.0

        # uses the mean flux across the mask as the data to fit to
        if f is None:
            f = np.nanmean(self.flux[mask,:], axis=0)
        f = f[reg] * scaling

        # gets the error on the flux
        if ferr is None:
            ferr = np.sqrt(np.nansum(self.flux_err[mask,:]**2,axis=0))/len(self.flux[mask,:])
        ferr = ferr[reg] * scaling

        vel = velocity[reg] + 0.0

        for i in range(ngauss):
            if i == 0:
                gmodel = Model(gaussian, prefix='g{}_'.format(i))
            else:
                gmodel += Model(gaussian, prefix='g{}_'.format(i))
        pars = gmodel.make_params()

        if mus is None:

            if ngauss>=6:
                mus = np.array([0, 30, -30, 100,-100, -150,
                                150, -200, 200],dtype=np.float32)
            else:
                fp,_ = find_peaks(f, width=15)
                best = np.argsort(f[fp])[-ngauss:]
                mus = vel[fp][best] + 0.0

                if len(best) < ngauss:
                    fp,_ = find_peaks(f, width=5)
                    best = np.argsort(f[fp])[-ngauss:]
                    mus = vel[fp][best] + 0.0
                if len(best) < ngauss:
                    mus=np.zeros(ngauss)

        for i in range(ngauss):
            pars['g{}_{}'.format(i, 'mu')].set(value=mus[i], min=vel.min()+40,
                                               max=vel.max()-40)
            pars['g{}_{}'.format(i, 'std')].set(value=10, min=0.1, max=200)
            pars['g{}_{}'.format(i, 'f')].set(value=20, min=0.01, max=400)

        init = gmodel.eval(pars, x=vel)

        out = gmodel.fit(f,
                         pars,
                         x=vel,
                         weights=1.0/ferr,
                         verbose=True,
                         max_nfev=3000)
        return vel, f, ferr, wave, lsf, out


    def new_lines(self, template, distance=150, prominence=None):
        """
        Marks peaks in a spectrum that are defined as `peaks` by
        scipy.signal.find_peaks. This function can be used to find new
        emission lines that may have appeared in-flare.

        Parameters
        ----------
        template : array
           The spectrum used to identify peaks in.
        distance : array or int, optional
           Required minimal horizontal distance in samples between
           neighboring peaks. Default is 150.
        prominance: array or int, optional
           Required prominence of peaks. If a list is passed in, the
           first element is interpreted as the minimal and the second,
           if supplied, as the maximal required prominence. Default
           is None.

        Returns
        -------
        peaks : np.array
           Array of args to where peaks in the data are identified.
        """
        peaks, _ = find_peaks(template, distance=distance, prominence=prominence)
        return peaks


    def identify_continuum(self):
        """
        Identifies region of the continuum (i.e. there are no strong
        emission features) in order to build a spectral energy distribution.

        Attributes
        ----------
        contiuum_mask : np.ndarray
           A binary mask for the template that corresponds to the continuum
           isolated regions.
        """
        cont = np.array([ [1067.506, 1070.062], [1074.662, 1076.533], [1078.881, 1082.167],
                          [1087.828, 1090.035], [1103.787, 1107.862], [1110.500, 1112.946],
                          [1113.618, 1117.377], [1119.548, 1121.622], [1125.255, 1126.923],
                          [1140.873, 1145.141], [1146.285, 1151.544], [1152.602, 1155.579],
                          [1159.276, 1163.222], [1164.565, 1173.959], [1178.669, 1188.363],
                          [1195.162, 1196.864],
                          #[1201.748, 1203.862], [1227.056, 1236.921],
                          [1262.399, 1263.967], [1268.559, 1273.974], [1281.396, 1287.493],
                          [1290.494, 1293.803], [1307.064, 1308.703], [1319.494, 1322.910],
                          [1330.349, 1332.884], [1337.703, 1341.813], [1341.116, 1350.847] ])
        cont_inds = np.ones(self.wavelength.shape, dtype=int)

        for i in range(len(self.wavelength)):
            for c in cont:
                inds = np.where((self.wavelength[i] >= c[0]) &
                                (self.wavelength[i] <= c[1]) )[0]
                cont_inds[i][inds] = 0

        self.continuum_mask = cont_inds


    def blackbody(self, x, T, scaling):
        """
        Blackbody equation in wavelength.

        Parameters
        ----------
        x : np.ndarray
           Wavelength array.
        T : float
           Temperature of the blackbody.
        scaling : float
           Scaling the flux to the blackbody.

        Returns
        -------
        bb : np.ndarray
           Log(Blackbody function).
        """
        T *= units.K
        x *= units.AA
        frac = 2.0 * constants.h * constants.c**2 / x**5
        exp = (constants.h * constants.c) / (x * constants.k_B * T)
        func =  frac * 1.0/(np.exp(exp) - 1.0)
        func = func.to(self.flux_units)
        return np.log10(func.value)*scaling
