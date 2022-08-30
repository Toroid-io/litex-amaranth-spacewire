import os
import subprocess

from amaranth import *

from litex import get_data_mod
from litex.soc.interconnect.csr import *
from litescope import LiteScopeAnalyzer

# AMARANTH SPACEWIRE --------------------------------------------------------------------------------

class SpWNode(Module, AutoCSR):
    def __init__(self, platform, src_freq, reset_freq, user_freq, pads, rx_tokens=7, tx_tokens=7, time_master=True):
        self.platform   = platform
        self._src_freq  = src_freq
        self._rstfreq = reset_freq
        self._userfreq = user_freq
        self._rx_tokens = rx_tokens
        self._tx_tokens = tx_tokens

        # Data/Strobe
        self.d_input = Signal()
        self.s_input = Signal()
        self.d_output = Signal()
        self.s_output = Signal()

        # Time functions
        self._time_master = time_master
        self.tick_input = Signal()
        self.tick_output = Signal()
        self.time_flags = Signal(2)
        self.time_value = Signal(6)

        # FIFO
        self.r_en = Signal()
        self.r_data = Signal(8)
        self.r_rdy = Signal()
        self.w_en = Signal()
        self.w_data = Signal(8)
        self.w_rdy = Signal()

        # Status signals
        self.link_state = Signal(3)
        self.link_error_flags = Signal(4)
        self.link_tx_credit = Signal(6)
        self.link_rx_credit = Signal(6)

        # Control signals
        self.soft_reset = Signal()
        self.switch_to_user_tx_freq = Signal()
        self.link_disabled = Signal()
        self.link_start = Signal()
        self.autostart = Signal()
        self.link_error_clear = Signal()

        self._status = CSRStatus(fields=[
            CSRField("data_available", size=1, offset=0),
            CSRField("link_state", size=4, offset=1),
            CSRField("link_error_flags", size=4, offset=5),
            CSRField("link_tx_credit", size=6, offset=9),
            CSRField("link_rx_credit", size=6, offset=15),
        ], name="status")
        self._time_value = CSRStatus(fields=[
            CSRField("time", size=6, offset=0),
            CSRField("flags", size=2, offset=6)
        ], name="time")
        self._fifo_r = CSRStatus(fields=[
            CSRField("data_r", size=8, offset=0)
        ], name="fifo_r")
        self._control = CSRStorage(fields=[
            CSRField("soft_reset", size=1, offset=0, pulse=True),
            CSRField("link_disabled", size=1, offset=1),
            CSRField("link_start", size=1, offset=2),
            CSRField("auto_start", size=1, offset=3),
            CSRField("user_freq", size=1, offset=4),
            CSRField("link_error_clear", size=1, offset=5, pulse=True),
        ], name="control")
        self._fifo_w = CSRStorage(fields=[
            CSRField("data_w", size=8, offset=0)
        ], name="fifo_w")

        # # #

        self.node_params = dict(
            # Clk / Rst.
            i_clk = ClockSignal("sys"),
            i_rst = ResetSignal("sys"),

            # Data/Strobe
            i_d_input = self.d_input,
            i_s_input = self.s_input,
            o_d_output = self.d_output,
            o_s_output = self.s_output,

            # Time functions
            i_tick_input = self.tick_input,
            o_tick_output = self.tick_output,
            o_time_flags = self.time_flags,
            o_time_value = self.time_value,

            # FIFO
            i_r_en = self.r_en,
            o_r_data = self.r_data,
            o_r_rdy = self.r_rdy,
            i_w_en = self.w_en,
            i_w_data = self.w_data,
            o_w_rdy = self.w_rdy,

            # Status signals
            o_link_state = self.link_state,
            o_link_error_flags = self.link_error_flags,
            o_link_tx_credit = self.link_tx_credit,
            o_link_rx_credit = self.link_rx_credit,

            # Control signals
            i_soft_reset = self.soft_reset,
            i_switch_to_user_tx_freq = self.switch_to_user_tx_freq,
            i_link_disabled = self.link_disabled,
            i_link_start = self.link_start,
            i_autostart = self.autostart,
            i_link_error_clear = self.link_error_clear,
        )

        self.comb += [
            self._status.fields.data_available.eq(self.r_rdy),
            self._status.fields.link_state.eq(self.link_state),
            self._status.fields.link_error_flags.eq(self.link_error_flags),
            self._status.fields.link_tx_credit.eq(self.link_tx_credit),
            self._status.fields.link_rx_credit.eq(self.link_rx_credit),

            self.soft_reset.eq(self._control.fields.soft_reset),
            self.link_disabled.eq(self._control.fields.link_disabled),
            self.link_start.eq(self._control.fields.link_start),
            self.autostart.eq(self._control.fields.auto_start),
            self.switch_to_user_tx_freq.eq(self._control.fields.user_freq),
            self.link_error_clear.eq(self._control.fields.link_error_clear),

            self.w_en.eq(self._fifo_w.re),
            self.w_data.eq(self._fifo_w.fields.data_w),

            self._fifo_r.fields.data_r.eq(self.r_data),
            self.r_en.eq(self._fifo_r.we)
        ]

        self.comb += [
            self.d_input.eq(pads.d_input),
            self.s_input.eq(pads.s_input),
            pads.d_output.eq(self.d_output),
            pads.s_output.eq(self.s_output)
        ]

    @staticmethod
    def elaborate(time_master, src_freq, reset_freq, user_freq, rx_tokens, tx_tokens, verilog_filename):
        cli_params = []
        if time_master:
            cli_params.append("--time-master")
        cli_params.append("--src-freq={}".format(src_freq))
        cli_params.append("--rx-tokens={}".format(rx_tokens))
        cli_params.append("--tx-tokens={}".format(tx_tokens))
        cli_params.append("--reset-freq={}".format(reset_freq))
        cli_params.append("--user-freq={}".format(user_freq))
        cli_params.append("generate")
        cli_params.append("--type=v")
        sdir = os.path.join(os.path.dirname(__file__), 'amaranth-spacewire')
        if subprocess.call(["python3", os.path.join(sdir, "cli.py"), *cli_params],
            stdout=open(verilog_filename, "w")):
            raise OSError("Unable to elaborate amaranth-spacewire core, please check your Amaranth/Yosys install")

    def do_finalize(self):
        verilog_filename = os.path.join(self.platform.output_dir, "gateware", "amaranth_spacewire.v")
        self.elaborate(
            time_master      = self._time_master,
            src_freq         = self._src_freq,
            reset_freq       = self._rstfreq,
            user_freq        = self._userfreq,
            rx_tokens        = self._rx_tokens,
            tx_tokens        = self._tx_tokens,
            verilog_filename = verilog_filename)
        self.platform.add_source(verilog_filename)
        self.specials += Instance("amaranth_spacewire_node", **self.node_params)
