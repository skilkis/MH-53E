#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" This file contains the class definition used to calculate the trim conditions of the CH53 Helicopter """

# http://python-control.readthedocs.io/en/latest/intro.html most likely this will be required

__author__ = ["San Kilkis"]

from globs import Constants, Attribute
from ch53_inertia import CH53Inertia
from trim import Trim
from timeit import default_timer as timer

import numpy as np
from scipy.optimize import fsolve
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FormatStrFormatter
from math import radians, sqrt, pi, degrees, cos, sin, asin, atan, exp
import os  # Necessary to determining the current working directory to save figures

_working_dir = os.getcwd()


class StabilityDerivatives(Constants):
    """ Computes the trim condition of the CH-53 based on current velocities

    :param u: Horizontal Flight Velocity in SI meter per second [m/s]
    :type u: float

    :param w: Vertical Flight Velocity in SI meter per second [m/s]
    :type w: float

    :param q: Pitch Rate in SI radian per second [rad/s]
    :type q: float

    :param theta_f: Fuselage Pitch Angle SI radian [rad]
    :type theta_f: float

    :param collective_pitch: Collective Pitch in SI degree [deg]
    :type collective_pitch: float

    :param longitudinal_cyclic: Longitudinal Cyclic in SI degree [deg]
    :type longitudinal_cyclic: float
    """

    def __init__(self, u=0.0, w=0.0, q=0.0, theta_f=0.0, collective_pitch=0.0, longitudinal_cyclic=0.0):
        self.u = float(u)  # Horizontal Velocity [m/s]
        self.w = float(w)  # Vertical Velocity [m/s]
        self.q = float(q)  # Pitch Rate [rad/s]
        self.theta_f = theta_f  # Fuselage Tilt-Angle (Positive up)
        self.collective_pitch = float(collective_pitch)
        self.longitudinal_cyclic = float(longitudinal_cyclic)

    @Attribute
    def velocity(self):
        """ The magnitude of the velocity vector, V,  in trim-condition.

        :return: Velocity in SI meter per second [m/s]
        :rtype: float
        """
        return sqrt(self.u**2 + self.w**2)

    @Attribute
    def alpha_control(self):
        """ Computes the Angle of Attack (AoA) of the control plane in SI radian [rad] depending on flight conditions.
        If the helicopter is in horizontal translation motion then the FPA (Flight Path Angle), gamma, is computed
        based on the angle formed by the horizontal and vertical velocities. Also, if the horizontal velocity is
        negative then 180 degrees (pi) is added to this angle to keep it consistent and in the correct quadrant. On the
        other hand, if the helicopter is in pure vertical motion, then the FPA is perpendicular to the horizon and
        a value of pi/2 or -pi/2 is returned depending on the direction of flight.

        :return: Control Plane Angle of Attack (AoA) in SI radian [rad]
        :rtype: float
        """
        if self.u != 0:
            gamma = atan(self.w / self.u)
            gamma = gamma if self.u > 0 else gamma + pi  # Adding 180 degrees if moving backwards
        else:  # Vertical Translation Case (Forcing Flight-Path Angle Vertical)
            gamma = pi / 2. if self.w > 0 else - pi / 2.

        # Subtracting the Flight Path Angle, gamma, to obtain the CP AoA
        alpha_c = self.longitudinal_cyclic - gamma

        return alpha_c

    @Attribute
    def advance_ratio(self):
        """ Computes the Advance Ratio, also referred to as the tip-speed ratio """
        return (self.velocity * cos(self.alpha_control)) / (self.main_rotor.omega * self.main_rotor.radius)

    @Attribute
    def inflow_ratio_control(self):
        """ Computes the Inflow Ratio in the Control Plane """
        return (self.velocity * sin(self.alpha_control)) / (self.main_rotor.omega * self.main_rotor.radius)

    def longitudinal_disk_tilt_func(self, lambda_i):
        """ Computes the longitudinal disk tilt, a1, utilizing an assumed value for the inflow ratio, lambda_i

        :param lambda_i: Inflow Ratio
        :type lambda_i: float
        """
        mu = self.advance_ratio
        theta0 = self.collective_pitch
        lambda_c = self.inflow_ratio_control
        omega = self.main_rotor.omega
        return (((8.0/3.0) * mu * theta0) - (2 * mu * (lambda_c + lambda_i)) -
                ((16.0/self.lock_number) * (self.q / omega))) / (1 - 0.5 * mu**2)

    def thrust_coefficient_elem(self, lambda_i):
        """ Thrust coefficient as defined by the Blade Element Momentum Theory

        :param lambda_i: Inflow Ratio
        :type lambda_i: float
        """
        mu = self.advance_ratio
        cla = self.lift_gradient
        sigma = self.main_rotor.solidity
        lambda_c = self.inflow_ratio_control
        theta0 = self.collective_pitch
        return (0.25 * cla * sigma) * ((2./3.) * theta0 * (1 + (1.5 * mu**2)) - (lambda_c + lambda_i))

    def thrust_coefficient_glau(self, lambda_i):
        """ Thrust coefficient as defined by the Glauert Theory

        :param lambda_i: Inflow Ratio
        :type lambda_i: float
        """
        a1 = self.longitudinal_disk_tilt_func(lambda_i)
        v = self.velocity
        omega = self.main_rotor.omega
        r = self.main_rotor.radius
        return 2 * lambda_i * sqrt(((v / (omega * r)) * cos(self.alpha_control - a1))**2 +
                                   ((v / (omega * r)) * sin(self.alpha_control - a1) + lambda_i)**2)

    @Attribute
    def hover_induced_velocity(self):
        """ Taken from the script `inducedvelocity.py` written for the previous assignment

        :return: Hover Induced Velocity in SI meter per second [m/s]
        """
        return sqrt(self.weight_mtow/(2*self.rho*pi*(self.main_rotor.radius ** 2)))

    @Attribute
    def inflow_ratio(self):
        """ Utilizes a numerical solver to compute the inflow ratio as discussed in the lecture slides unless a pure
        hover is input as the current trim-condition. In the pure-hover case, the inflow ratio during hover is returned

        :return: Inflow Ratio
        :rtype: float
        """

        def func(lambda_i, *args):

            instance, status = args
            diff = instance.thrust_coefficient_elem(lambda_i) - instance.thrust_coefficient_glau(lambda_i)
            return diff

        if self.velocity == 0:
            ratio = self.hover_induced_velocity / (self.main_rotor.omega * self.main_rotor.radius)
        else:
            ratio = float((fsolve(func, x0=np.array([2e-2]), args=(self, 'instance_passed'))[0]))

        return ratio

    @Attribute
    def longitudinal_disk_tilt(self):
        return self.longitudinal_disk_tilt_func(self.inflow_ratio)

    @Attribute
    def thrust(self):
        omega = self.main_rotor.omega
        r = self.main_rotor.radius
        return self.thrust_coefficient_elem(self.inflow_ratio) * self.rho * (omega * r)**2 * pi * r**2

    @Attribute
    def ch53_inertia(self):
        """ Instantiating the :class:`CH53Inertia` in a lazy-attribute to provide geometry parameters as required

        :rtype: CH53Inertia
        """
        return CH53Inertia()

    @Attribute
    def inertia(self):
        """ Computes the Mass Moment of Inertia of the CH-53 utilizing the method discussed in Assignment I and the
        :class:`CH53Inertia`.

        :return: Total Mass Moment of Inertia w.r.t the center of gravity in SI kilogram meter squared [kg m^2]
        :rtype: Inertia
        """
        return self.ch53_inertia.get_inertia()

    @Attribute
    def rotor_distance_to_cg(self):
        """ Computes the z-axis distance of the main-rotor centroid to the center of gravity (C.G) of the CH-53

        :return: Distance of the Main Rotor to the Center of Gravity (C.G.) on the z-axis in SI meter [m]
        :rtype: float
        """

        cg = self.ch53_inertia.get_cg()
        motor_position = self.ch53_inertia.main_rotor.position
        return abs(motor_position.z - cg.z)

    @Attribute
    def drag(self):
        """ Computes the drag force acting on the CH-53 at the current trim-state utilizing the Equivalent Flat Plate
        Area as discussed in Assignment I

        :return: Drag Force in SI Newton [N]
        :rtype: float
        """
        return self.flat_plate_area*0.5*self.rho*(self.velocity**2)

    @property
    def u_dot(self):
        """ Computes the acceleration on the x-axis of the CH-53 (body-axis) utilizing force equilibrium

        :return: Acceleration on the x-axis in SI meter per second squared [m/s^2]
        :rtype: float
        """
        drag = ((self.drag * self.u)/(self.mass_mtow * self.velocity)) if self.velocity != 0 else 0
        return -self.g * sin(self.theta_f) - drag + (self.thrust / self.mass_mtow) * \
               sin(self.longitudinal_cyclic - self.longitudinal_disk_tilt) - self.q * self.w

    @property
    def w_dot(self):
        """ Computes the acceleration on the z-axis of the CH-53 (body-axis) utilizing force equilibrium, NOTE: The
        z-axis is defined as positive in the nadir direction, thus a positive value translates to a sink-rate.

        :return: Acceleration on the z-axis in SI meter per second squared [m/s^2]
        :rtype: float
        """
        drag = ((self.drag * self.w)/(self.mass_mtow * self.velocity)) if self.velocity != 0 else 0
        return self.g * cos(self.theta_f) - drag - (self.thrust / self.mass_mtow) * \
               cos(self.longitudinal_cyclic - self.longitudinal_disk_tilt) + self.q * self.u

    @Attribute
    def q_dot(self):
        return (-self.thrust / self.inertia.yy) * self.rotor_distance_to_cg * \
               sin(self.longitudinal_cyclic - self.longitudinal_disk_tilt)

    @Attribute
    def theta_f_dot(self):
        return self.q

    @Attribute
    def u_derivatives(self):
        u_dot = []
        w_dot = []
        q_dot = []
        theta_f_dot = []
        delta_u = np.linspace(-10, 10, 100)
        for i in delta_u:
            case = StabilityDerivatives(u=self.u + i, w=self.w, q=self.q, theta_f=self.theta_f,
                                        collective_pitch=self.collective_pitch,
                                        longitudinal_cyclic=self.longitudinal_cyclic)
            u_dot.append(case.u_dot / i)
            w_dot.append(case.w_dot / i)
            q_dot.append(case.q_dot / i)
            theta_f_dot.append(case.theta_f_dot / i)

        return np.mean(u_dot), np.mean(w_dot), np.mean(q_dot), np.mean(theta_f_dot)

    @Attribute
    def w_derivatives(self):
        u_dot = []
        w_dot = []
        q_dot = []
        theta_f_dot = []
        delta_u = np.linspace(-10, 10, 100)
        for i in delta_u:
            case = StabilityDerivatives(u=self.u, w=self.w + i, q=self.q, theta_f=self.theta_f,
                                        collective_pitch=self.collective_pitch,
                                        longitudinal_cyclic=self.longitudinal_cyclic)
            u_dot.append(case.u_dot / i)
            w_dot.append(case.w_dot / i)
            q_dot.append(case.q_dot / i)
            theta_f_dot.append(case.theta_f_dot / i)

        return np.mean(u_dot), np.mean(w_dot), np.mean(q_dot), np.mean(theta_f_dot)

    @Attribute
    def q_derivatives(self):
        u_dot = []
        w_dot = []
        q_dot = []
        theta_f_dot = []
        delta_u = np.linspace(radians(-10), radians(10), 100)
        for i in delta_u:
            case = StabilityDerivatives(u=self.u, w=self.w, q=self.q + i, theta_f=self.theta_f,
                                        collective_pitch=self.collective_pitch,
                                        longitudinal_cyclic=self.longitudinal_cyclic)
            u_dot.append(case.u_dot / i)
            w_dot.append(case.w_dot / i)
            q_dot.append(case.q_dot / i)
            theta_f_dot.append(case.theta_f_dot / i)

        return np.mean(u_dot), np.mean(w_dot), np.mean(q_dot), np.mean(theta_f_dot)

    @Attribute
    def theta_f_derivatives(self):
        u_dot = []
        w_dot = []
        q_dot = []
        theta_f_dot = []
        delta_u = np.linspace(radians(-10), radians(10), 100)
        for i in delta_u:
            case = StabilityDerivatives(u=self.u, w=self.w, q=self.q, theta_f=self.theta_f + i,
                                        collective_pitch=self.collective_pitch,
                                        longitudinal_cyclic=self.longitudinal_cyclic)
            u_dot.append(case.u_dot / i)
            w_dot.append(case.w_dot / i)
            q_dot.append(case.q_dot / i)
            theta_f_dot.append(case.theta_f_dot / i)

        return np.mean(u_dot), np.mean(w_dot), np.mean(q_dot), np.mean(theta_f_dot)

    @Attribute
    def collective_derivatives(self):
        u_dot = []
        w_dot = []
        q_dot = []
        theta_f_dot = []
        delta_u = np.linspace(radians(-10), radians(10), 100)
        for i in delta_u:
            case = StabilityDerivatives(u=self.u, w=self.w, q=self.q, theta_f=self.theta_f,
                                        collective_pitch=self.collective_pitch + i,
                                        longitudinal_cyclic=self.longitudinal_cyclic)
            u_dot.append(case.u_dot / i)
            w_dot.append(case.w_dot / i)
            q_dot.append(case.q_dot / i)
            theta_f_dot.append(case.theta_f_dot / i)

        return np.mean(u_dot), np.mean(w_dot), np.mean(q_dot), np.mean(theta_f_dot)

    @Attribute
    def cyclic_derivatives(self):
        u_dot = []
        w_dot = []
        q_dot = []
        theta_f_dot = []
        delta_u = np.linspace(radians(-10), radians(10), 100)
        for i in delta_u:
            case = StabilityDerivatives(u=self.u, w=self.w, q=self.q, theta_f=self.theta_f,
                                        collective_pitch=self.collective_pitch,
                                        longitudinal_cyclic=self.longitudinal_cyclic + i)
            u_dot.append(case.u_dot / i)
            w_dot.append(case.w_dot / i)
            q_dot.append(case.q_dot / i)
            theta_f_dot.append(case.theta_f_dot / i)

        return np.mean(u_dot), np.mean(w_dot), np.mean(q_dot), np.mean(theta_f_dot)

    @staticmethod
    def plot_euler_error():

        fig = plt.figure('EulerError')
        plt.style.use('ggplot')

        # Values used for the Exact Solution
        x_final = 4
        x_exact = np.linspace(0, x_final, 100)
        y_exact = [exp(num) for num in x_exact]

        plt.plot(x_exact, y_exact, label='Exact Solution')

        # Values used for the Numerical Forward Euler Integration
        num_points = [5, 9, 19]
        for i in range(0, 3):
            x = np.linspace(0, x_final, num_points[i])
            delta_x = x[1] - x[0]
            y_euler = [exp(0)]
            y_euler = y_euler + [exp(x[i - 1]) * delta_x + exp(x[i - 1]) for i in range(1, len(x))]

            plt.plot(x, y_euler, linestyle=':', label='F. Euler h = %1.4f' % delta_x, marker='x')

        plt.xlabel(r'$x$ [-]')
        plt.ylabel(r'$f\left(x\right) = \mathrm{e}^x$ [-]')
        plt.title(r'Forward Euler Numerical Integration of $f\left(x\right) = e^{x}$')
        plt.legend(loc='best')
        plt.show()
        fig.savefig(fname=os.path.join(_working_dir, 'Figures', '%s.pdf' % fig.get_label()), format='pdf')

    def plot_response(self):

        time = np.linspace(0, 10, 1000)
        delta_t = time[1] - time[0]
        cyclic_input = [0]
        u = [self.u]
        w = [self.w]
        q = [self.q]
        theta_f = [self.theta_f]
        current_case = self

        # Forward Euler Integration
        start = timer()
        for i in range(1, len(time)):
            u.append(current_case.u + current_case.u_dot * delta_t)
            w.append(current_case.w + current_case.w_dot * delta_t)
            q.append(current_case.q + current_case.q_dot * delta_t)
            theta_f.append(current_case.theta_f + current_case.theta_f_dot * delta_t)

            # Control Inputs based on Initial Conditions
            if 0.5 < time[i] < 1.0:
                cyclic_input.append(self.longitudinal_cyclic + radians(1.0))
            else:
                cyclic_input.append(self.longitudinal_cyclic)

            current_case = StabilityDerivatives(u=u[i], w=w[i], q=q[i], theta_f=theta_f[i],
                                                longitudinal_cyclic=cyclic_input[i],
                                                collective_pitch=self.collective_pitch)

        end = timer()
        print '\nIntegration Performed \n' + 'Duration: %1.5f [s]\n' % (end - start)

        # Plotting Response
        fig = plt.figure('EulerResponseVelocities')
        plt.style.use('ggplot')
        gs = gridspec.GridSpec(2, 1, top=0.9)
        fig.set_tight_layout('False')

        cyc_plot = fig.add_subplot(gs[0, 0])
        cyc_plot.plot(time, [degrees(rad) for rad in cyclic_input])
        cyc_plot.set_ylabel(r'Lon. Cyclic [deg]')
        cyc_plot.set_xlabel('')
        cyc_plot.yaxis.set_major_formatter(FormatStrFormatter('%.3f'))

        vel_plot = fig.add_subplot(gs[1, 0])
        vel_plot.plot(time, u, label='Horizontal')
        vel_plot.plot(time, w, label='Vertical')
        vel_plot.set_ylabel(r'Velocity [m/s]')
        vel_plot.set_xlabel('')
        vel_plot.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))
        vel_plot.legend(loc='best')

        # Creating Labels & Saving Figure
        plt.suptitle(r'Translational Response as a Function of Time')
        plt.xlabel(r'Time [s]')
        plt.show()
        fig.savefig(fname=os.path.join(_working_dir, 'Figures', '%s.pdf' % fig.get_label()), format='pdf')

        # ----------------------------------------------------------------------------------------------------------- #

        # Creating Second Figure
        fig = plt.figure('EulerResponseAngles')
        plt.style.use('ggplot')
        fig.set_tight_layout('False')
        gs = gridspec.GridSpec(3, 1, top=0.925, left=0.15)

        cyc_plot = fig.add_subplot(gs[0, 0])
        cyc_plot.plot(time, [degrees(rad) for rad in cyclic_input])
        cyc_plot.set_ylabel(r'$\theta_{ls}$ [deg]')
        cyc_plot.yaxis.set_major_formatter(FormatStrFormatter('%.3f'))

        q_plot = fig.add_subplot(gs[1, 0])
        q_plot.plot(time, [degrees(rad) for rad in q])
        q_plot.set_ylabel(r'$q$ [deg/s]')
        q_plot.set_xlabel('')
        # q_plot.yaxis.set_major_formatter(FormatStrFormatter('%.1E'))
        q_plot.yaxis.set_major_formatter(FormatStrFormatter('%.3f'))

        theta_plot = fig.add_subplot(gs[2, 0])
        theta_plot.plot(time, [degrees(rad) for rad in theta_f])
        theta_plot.set_ylabel(r'$\theta_f$ [deg]')
        theta_plot.set_xlabel('')
        theta_plot.yaxis.set_major_formatter(FormatStrFormatter('%.3f'))

        # Creating Labels & Saving Figure
        plt.suptitle(r'Angular Response as a Function of Time')
        plt.xlabel(r'Time [s]')
        plt.show()
        fig.savefig(fname=os.path.join(_working_dir, 'Figures', '%s.pdf' % fig.get_label()), format='pdf')

        return 'Figures Plotted and Saved'


if __name__ == '__main__':
    trim_case = Trim(10)  # Hover Trim case at V=0
    u = trim_case.velocity*cos(trim_case.fuselage_tilt)
    w = trim_case.velocity*sin(trim_case.fuselage_tilt)
    obj = StabilityDerivatives(u=u, w=w, q=0, theta_f=trim_case.fuselage_tilt,
                               collective_pitch=trim_case.collective_pitch,
                               longitudinal_cyclic=trim_case.longitudinal_cyclic)
    obj.plot_response()
    # print 'State Variables = u, w, q, theta_f'
    # print 'u Derivatives ', obj.u_derivatives
    # print 'w Derivatives ', obj.w_derivatives
    # print 'q Derivatives ', obj.q_derivatives
    # print 'theta_f Derivatives ', obj.theta_f_derivatives
    # print 'collective Derivatives ', obj.collective_derivatives
    # print 'cyclic Derivatives ', obj.cyclic_derivatives
