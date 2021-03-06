from myhdl import *
import os
import numpy as np
import spectrum
from scipy import signal

verilogtb = """
    localparam VAR_ACC_WIDTH = (CICRATE == 10) ? 34 : (CICRATE == 13) ? 34 : (CICRATE == 5) ? 41 : 39; // Last is default rate of 8
    localparam CIC_ACC_WIDTH = (CICRATE == 10) ? 28 : (CICRATE == 13) ? 30 : (CICRATE == 5) ? 25 : 27; // Last is default rate of 8
    reg clk;
    reg flushed1;
    reg flushed2;
    reg signed [31:0] freq;
    reg signed [CORDIC_IN_WIDTH-1:0] in_data;
    reg [5:0] var_decimation;
    wire signed [CORDIC_IN_WIDTH+CORDIC_EXTRA_BITS:0] out_data_I;
    wire signed [CORDIC_IN_WIDTH+CORDIC_EXTRA_BITS:0] in_data_I;
    wire signed [CORDIC_IN_WIDTH+CORDIC_EXTRA_BITS:0] out_data_Q;
    wire decimA_avail;
    wire decimB_avail;
    wire signed [CIC_OUT_WIDTH-1:0] decimA_real;
    wire signed [CIC_OUT_WIDTH-1:0] out_decimA_real;
    wire signed [VAR_OUT_WIDTH-1:0] decimB_real;

    initial begin
        $from_myhdl(clk, freq, in_data, flushed1, flushed2, var_decimation);
        $to_myhdl(out_data_I,out_data_Q,decimA_avail,decimA_real,decimB_avail,decimB_real);
        $dumpfile("test_rx2.lxt");
        $dumpvars(0, test_rx2);
    end

cordic #(.IN_WIDTH(CORDIC_IN_WIDTH), .EXTRA_BITS(CORDIC_EXTRA_BITS)) cordic_i (
    .clock(clk), 
    .frequency(freq), 
    .in_data(in_data),
    .out_data_I(out_data_I),
    .out_data_Q(out_data_Q)           
);
assign in_data_I = flushed1 ? out_data_I : 0;
cic #(.STAGES(CIC_STAGES), .DECIMATION(CIC_DECIMATION), .IN_WIDTH(CORDIC_IN_WIDTH+CORDIC_EXTRA_BITS+1), .ACC_WIDTH(CIC_ACC_WIDTH), .OUT_WIDTH(CIC_OUT_WIDTH)) cic_i (
    .clock(clk),
    .in_strobe(1'b1),
    .out_strobe(decimA_avail),
    .in_data(in_data_I),
    .out_data(out_decimA_real)
);
assign decimA_real = flushed2 ? out_decimA_real : 0;
varcic #(.STAGES(VAR_STAGES), .IN_WIDTH(CIC_OUT_WIDTH), .ACC_WIDTH(VAR_ACC_WIDTH), .OUT_WIDTH(VAR_OUT_WIDTH), .CICRATE(CICRATE))
  varcic_i(
    .clock(clk),
    .in_strobe(decimA_avail),
    .decimation(var_decimation),
    .out_strobe(decimB_avail),
    .in_data(decimA_real),
    .out_data(decimB_real)
    );


endmodule
"""



class Test(object):

    def __init__(self,
        cordic_in_width=12,
        cordic_extra_bits=5,
        cic_stages=3,
        cic_decimation=8,
        cic_out_width=14,
        var_stages=5,
        var_out_width=16,
        var_cic_rate=8,
        var_decimation=12,
        ampl=1.0):

        self.cordic_in_width=cordic_in_width
        self.cordic_extra_bits=cordic_extra_bits
        self.cic_stages=cic_stages
        self.cic_decimation=cic_decimation
        self.cic_out_width=cic_out_width
        self.var_stages=var_stages
        self.var_cic_rate=var_cic_rate
        self.var_out_width=var_out_width
        self.var_decimation=var_decimation

        f = open("test_rx2.v","w")
        f.write("`timescale 1ps / 1ps\nmodule test_rx2;\n")
        f.write("    localparam CORDIC_IN_WIDTH={0};\n".format(self.cordic_in_width))
        f.write("    localparam CORDIC_EXTRA_BITS={0};\n".format(self.cordic_extra_bits))
        f.write("    localparam CIC_STAGES={0};\n".format(self.cic_stages))
        f.write("    localparam CIC_DECIMATION={0};\n".format(self.cic_decimation))
        f.write("    localparam CIC_OUT_WIDTH={0};\n".format(self.cic_out_width))
        f.write("    localparam VAR_STAGES={0};\n".format(self.var_stages))
        f.write("    localparam CICRATE={0};\n".format(self.var_cic_rate))
        f.write("    localparam VAR_OUT_WIDTH={0};\n".format(self.var_out_width))


        f.write(verilogtb)
        f.close()

        self.sampling_freq = 73728000
        self.rx_freq = 10000000
        self.sigfreq = 10020000


        module = 'rx2'
        self.testbench = 'test_%s' % module

        srcs = []

        srcs.append("../rtl/cordic.v")
        srcs.append("../rtl/varcic.v")
        srcs.append("../rtl/cic.v")
        srcs.append("../rtl/cic_comb.v")
        srcs.append("../rtl/cic_integrator.v")

        srcs.append("%s.v" % self.testbench)

        src = ' '.join(srcs)

        self.build_cmd = "iverilog -g2012 -o %s.vvp %s" % (self.testbench,src)
        print(self.build_cmd)

        self.res = np.zeros(2048)


        ## m2 and m3 from rtl
        ##m2 = 1876499845  76.8
        m2 = 1954687338  # 73.728
        m3 = 16777216

        self.rx_phase = (self.rx_freq * m2 + m3) >> 25

        self.dt = 1.0/self.sampling_freq

        self.offset = 0
        if ampl >= 0.0:
            self.scale = ampl*((2**(self.cordic_in_width-1))-1)    
        else:
            self.scale = abs(ampl)

        ## Handle 1 bit
        if self.scale <= 0.5: self.offset = self.scale




    def Sig(self,i):

        return int(round( (self.scale*np.sin(2*np.pi*self.sigfreq*i*self.dt)+self.offset) ))

    def bench(self):

        # Inputs
        clk = Signal(bool(0))
     
        maxv = 2**31
        freq = Signal(intbv(0,min=-maxv,max=maxv))
        maxv = 2**(self.cordic_in_width+self.cordic_extra_bits+1-1)
        out_data_I = Signal(intbv(0,min=-maxv,max=maxv))
        out_data_Q = Signal(intbv(0,min=-maxv,max=maxv))
        maxv = 2**(self.cordic_in_width-1)
        in_data = Signal(intbv(0,min=-maxv,max=maxv))

        decimA_avail = Signal(bool(0))
        maxv = 2**(self.cic_out_width-1)
        decimA_real = Signal(intbv(0,min=-maxv,max=maxv))

        decimB_avail = Signal(bool(0))
        maxv = 2**(self.var_out_width-1)
        decimB_real = Signal(intbv(0,min=-maxv,max=maxv))

        var_decimation = Signal(intbv(0)[6:])

        flushed1 = Signal(bool(0))
        flushed2 = Signal(bool(0))

        # DUT
        if os.system(self.build_cmd):
            raise Exception("Error running build command")

        dut = Cosimulation(
            "vvp -m myhdl %s.vvp -lxt2" % self.testbench,
            clk=clk,
            flushed1=flushed1,
            flushed2=flushed2,
            freq=freq,
            in_data=in_data,
            out_data_I=out_data_I,
            out_data_Q=out_data_Q,
            decimA_avail=decimA_avail,
            decimA_real=decimA_real,
            decimB_avail=decimB_avail,
            decimB_real=decimB_real,
            var_decimation=var_decimation
        )

        @always(delay(int((self.dt*1e12)/2)))
        def clkgen():
            clk.next = not clk

        @instance
        def check():

            freq.next = self.rx_phase
            in_data.next = 0x00
            flushed1.next = 0x00
            flushed2.next = 0x00
            var_decimation.next = self.var_decimation
           
            for i in range(128):
                if i == 20: flushed1.next = 0x1
                if i == 64: flushed2.next = 0x1
                in_data.next = self.Sig(i)
                yield negedge(clk)

            i = 128
            j = 0
            while j < 2048:
                in_data.next = self.Sig(i)
                i = i + 1
                if decimB_avail:
                    self.res[j] = decimB_real
                    j = j + 1
                yield clk.negedge
                if (i % 1024) == 0: print(j)
     
            raise StopSimulation

        return dut, clkgen, check

    def test_bench(self):
        sim = Simulation(self.bench())
        sim.run()
        s = spectrum.Spectrum(self.res,self.dt*self.cic_decimation*self.var_decimation,window=signal.flattop)
        ##peaks = s.findPeaks(order=4,clipdb=90)
        ##s.printPeaks(peaks)
        s.plot()


if __name__ == '__main__':
    print("Running test...")
    ## Set ampl to -0.5 for just 1 bit changing
    t = Test(cic_out_width=16,ampl=0.9)
    t.test_bench()
    ##t = Test(16,7)
    ##t.test_bench()

    
        


                

        

