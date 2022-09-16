import os
import subprocess

from amaranth import *

from litex import get_data_mod
from litex.soc.interconnect.csr import *
from litescope import LiteScopeAnalyzer

# AMARANTH SPACEWIRE --------------------------------------------------------------------------------

class SpWNode(Module, AutoCSR):
    def __init__(self, platform, src_freq, reset_freq, tx_freq, pads, fifo_depth_tokens=7):
        self.platform   = platform
        self._src_freq  = src_freq
        self._rstfreq = reset_freq
        self._txfreq = tx_freq
        self._fifo_depth_tokens = fifo_depth_tokens

        # Data/Strobe
        self.data_input = Signal()
        self.strobe_input = Signal()
        self.data_output = Signal()
        self.strobe_output = Signal()

        # FIFO
        self.r_en = Signal()
        self.r_data = Signal(9)
        self.r_rdy = Signal()
        self.w_en = Signal()
        self.w_data = Signal(9)
        self.w_rdy = Signal()

        # Status signals
        self.link_state = Signal(3)
        self.link_error_flags = Signal(4)
        self.link_tx_credit = Signal(6)
        self.link_rx_credit = Signal(6)

        # Control signals
        self.tx_switch_freq = Signal()
        self.link_disabled = Signal()
        self.link_start = Signal()
        self.autostart = Signal()

        self._status = CSRStatus(fields=[
            CSRField("read_ready", size=1, offset=0),
            CSRField("write_ready", size=1, offset=1),
            CSRField("link_state", size=4, offset=2),
            CSRField("link_error_flags", size=4, offset=6),
            CSRField("link_tx_credit", size=6, offset=10),
            CSRField("link_rx_credit", size=6, offset=16),
        ], name="status")
        self._fifo_r = CSRStatus(fields=[
            CSRField("data", size=9, offset=0)
        ], name="fifo_r")
        self._control = CSRStorage(fields=[
            CSRField("link_disabled", size=1, offset=0),
            CSRField("link_start", size=1, offset=1),
            CSRField("auto_start", size=1, offset=2),
            CSRField("tx_switch_freq", size=1, offset=3),
        ], name="control")
        self._fifo_w = CSRStorage(fields=[
            CSRField("data", size=9, offset=0)
        ], name="fifo_w")

        # # #

        self.node_params = dict(
            # Clk / Rst.
            i_clk = ClockSignal("sys"),
            i_rst = ResetSignal("sys"),

            # Data/Strobe
            i_data_input = self.data_input,
            i_strobe_input = self.strobe_input,
            o_data_output = self.data_output,
            o_strobe_output = self.strobe_output,

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
            i_tx_switch_freq = self.tx_switch_freq,
            i_link_disabled = self.link_disabled,
            i_link_start = self.link_start,
            i_autostart = self.autostart,
        )

        self.comb += [
            self._status.fields.read_ready.eq(self.r_rdy),
            self._status.fields.write_ready.eq(self.w_rdy),
            self._status.fields.link_state.eq(self.link_state),
            self._status.fields.link_error_flags.eq(self.link_error_flags),
            self._status.fields.link_tx_credit.eq(self.link_tx_credit),
            self._status.fields.link_rx_credit.eq(self.link_rx_credit),

            self.link_disabled.eq(self._control.fields.link_disabled),
            self.link_start.eq(self._control.fields.link_start),
            self.autostart.eq(self._control.fields.auto_start),
            self.tx_switch_freq.eq(self._control.fields.tx_switch_freq),

            self.w_en.eq(self._fifo_w.re),
            self.w_data.eq(self._fifo_w.fields.data),

            self._fifo_r.fields.data.eq(self.r_data),
            self.r_en.eq(self._fifo_r.we)
        ]

        self.comb += [
            self.data_input.eq(pads.data_input),
            self.strobe_input.eq(pads.strobe_input),
            pads.data_output.eq(self.data_output),
            pads.strobe_output.eq(self.strobe_output)
        ]

    @staticmethod
    def elaborate(src_freq, reset_freq, tx_freq, fifo_depth_tokens, verilog_filename):
        cli_params = []
        cli_params.append("--src-freq={}".format(src_freq))
        cli_params.append("--reset-freq={}".format(reset_freq))
        cli_params.append("--tx-freq={}".format(tx_freq))
        cli_params.append("--fifo-tokens={}".format(fifo_depth_tokens))
        cli_params.append("generate")
        cli_params.append("--type=v")
        sdir = os.path.join(os.path.dirname(__file__), 'amaranth-spacewire')
        if subprocess.call(["python3", os.path.join(sdir, "cli.py"), *cli_params],
            stdout=open(verilog_filename, "w")):
            raise OSError("Unable to elaborate amaranth-spacewire core, please check your Amaranth/Yosys install")

    def do_finalize(self):
        verilog_filename = os.path.join(self.platform.output_dir, "gateware", "amaranth_spacewire.v")
        self.elaborate(
            src_freq            = self._src_freq,
            reset_freq          = self._rstfreq,
            tx_freq             = self._txfreq,
            fifo_depth_tokens   = self._fifo_depth_tokens,
            verilog_filename = verilog_filename)
        self.platform.add_source(verilog_filename)
        self.specials += Instance("amaranth_spacewire_node", **self.node_params)
