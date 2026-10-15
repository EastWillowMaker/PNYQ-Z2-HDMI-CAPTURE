`timescale 1ns/1ps
// Exercise the real synthesized HLS pair with no following source frame.
module hls_drain_tb;
parameter WIDTH=8, HEIGHT=4, INPUT_STALL=0, OUTPUT_STALL=0;
reg clk=0, resetn=0, valid=0, sof=0, eol=0;
reg [23:0] data=0;
wire ready, cv, cr, cu, cl, pv, pu, pl;
wire [23:0] cd;
wire [2:0] ck, cs;
wire [31:0] pd;
wire [3:0] pk, ps;
reg [6:0] awaddr=0;
reg awvalid=0, wvalid=0;
reg [31:0] wdata=0;
wire awready, wready, bvalid;
integer cycles=0, input_count=0, color_count=0, words=0;
integer color_eol=0, packed_eol=0, color_sof=0, packed_sof=0;
wire output_ready=!OUTPUT_STALL || (cycles%13<8);
always #3.5 clk=~clk;
always @(negedge clk) cycles=cycles+1;

color_convert color(
 .ap_clk(clk),.ap_rst_n(resetn),
 .stream_in_24_TDATA(data),.stream_in_24_TVALID(valid),.stream_in_24_TREADY(ready),
 .stream_in_24_TKEEP(3'b111),.stream_in_24_TSTRB(3'b111),.stream_in_24_TUSER(sof),.stream_in_24_TLAST(eol),
 .stream_out_24_TDATA(cd),.stream_out_24_TVALID(cv),.stream_out_24_TREADY(cr),
 .stream_out_24_TKEEP(ck),.stream_out_24_TSTRB(cs),.stream_out_24_TUSER(cu),.stream_out_24_TLAST(cl),
 .s_axi_control_AWVALID(awvalid),.s_axi_control_AWADDR(awaddr),.s_axi_control_AWREADY(awready),
 .s_axi_control_WVALID(wvalid),.s_axi_control_WDATA(wdata),.s_axi_control_WSTRB(4'b1111),
 .s_axi_control_WREADY(wready),.s_axi_control_BVALID(bvalid),
 .s_axi_control_ARVALID(1'b0),.s_axi_control_ARADDR(7'b0),
 .s_axi_control_RREADY(1'b1),.s_axi_control_BREADY(1'b1));
pixel_pack pack(
 .ap_clk(clk),.ap_rst_n(resetn),
 .stream_in_24_TDATA(cd),.stream_in_24_TVALID(cv),.stream_in_24_TREADY(cr),
 .stream_in_24_TKEEP(ck),.stream_in_24_TSTRB(cs),.stream_in_24_TUSER(cu),.stream_in_24_TLAST(cl),
 .stream_out_32_TDATA(pd),.stream_out_32_TVALID(pv),.stream_out_32_TREADY(output_ready),
 .stream_out_32_TKEEP(pk),.stream_out_32_TSTRB(ps),.stream_out_32_TUSER(pu),.stream_out_32_TLAST(pl),
 .s_axi_control_AWVALID(1'b0),.s_axi_control_AWADDR(5'b0),
 .s_axi_control_WVALID(1'b0),.s_axi_control_WDATA(32'b0),.s_axi_control_WSTRB(4'b0),
 .s_axi_control_ARVALID(1'b0),.s_axi_control_ARADDR(5'b0),
 .s_axi_control_RREADY(1'b1),.s_axi_control_BREADY(1'b1));

function [23:0] pixel_value;
 input integer index;
 begin pixel_value=(index*24'h1f5b73)^24'h804020; end
endfunction
function [7:0] byte_value;
 input integer index;
 reg [23:0] pixel;
 begin pixel=pixel_value(index/3); byte_value=pixel >> (8*(index%3)); end
endfunction
wire [31:0] expected_word={byte_value(words*4+3),byte_value(words*4+2),
                          byte_value(words*4+1),byte_value(words*4)};
reg stalled=0;
reg [33:0] held_output;
always @(posedge clk) if(resetn) begin
 if(valid && ready) input_count=input_count+1;
 if(cv && cr) begin
  if(cd !== pixel_value(color_count) || cu !== (color_count==0) || cl !== (color_count%WIDTH==WIDTH-1))
   $fatal(1,"Color pixel or boundary mismatch at %0d",color_count);
  color_count=color_count+1; color_eol=color_eol+cl; color_sof=color_sof+cu;
 end
 if(stalled && (!pv || {pd,pu,pl} !== held_output)) $fatal(1,"Output changed under backpressure");
 stalled=pv && !output_ready; held_output={pd,pu,pl};
 if(pv && output_ready) begin
  if(pd !== expected_word || pu !== (words==0) || pl !== (words%(WIDTH*3/4)==WIDTH*3/4-1))
   $fatal(1,"Packed data or boundary mismatch at %0d",words);
  words=words+1; packed_eol=packed_eol+pl; packed_sof=packed_sof+pu;
 end
end

task coefficient;
 input [6:0] address;
 begin
  @(negedge clk); awaddr=address; awvalid=1;
  @(posedge clk); while(!awready) @(posedge clk);
  @(negedge clk); awvalid=0; wdata=256; wvalid=1;
  @(posedge clk); while(!wready) @(posedge clk);
  @(negedge clk); wvalid=0;
  @(posedge clk); while(!bvalid) @(posedge clk);
 end
endtask
task send_pixel;
 input integer index;
 begin
  if(INPUT_STALL && index%7==0) begin
   @(negedge clk); valid=0;
   repeat(3) @(negedge clk);
  end
  @(negedge clk); valid=1; data=pixel_value(index);
  sof=(index==0); eol=(index%WIDTH==WIDTH-1);
  @(posedge clk); while(!ready) @(posedge clk);
 end
endtask
integer i;
initial begin
 if(WIDTH%4!=0 || WIDTH<4 || HEIGHT<1) $fatal(1,"Unsupported test geometry");
 repeat(20) @(negedge clk); resetn=1;
 // Actual AXI-Lite writes set a bit-exact identity matrix (Q2.8 coefficients).
 coefficient(7'h10); coefficient(7'h30); coefficient(7'h50);
 for(i=0;i<WIDTH*HEIGHT;i=i+1) send_pixel(i);
 @(negedge clk); valid=0; sof=0; eol=0;
 // Deliberately provide no next SOF or dummy pixels to flush the pipeline.
 repeat(200) @(negedge clk);
 $display("DRAIN input=%0d color_pixels=%0d packed_words=%0d color_eol=%0d packed_eol=%0d",input_count,color_count,words,color_eol,packed_eol);
 if(input_count!=WIDTH*HEIGHT || color_count!=WIDTH*HEIGHT || words!=WIDTH*HEIGHT*3/4 ||
    color_eol!=HEIGHT || packed_eol!=HEIGHT || color_sof!=1 || packed_sof!=1)
  $fatal(1,"Isolated whole frame did not drain");
 $display("PASS %0dx%0d input_stall=%0d output_stall=%0d",WIDTH,HEIGHT,INPUT_STALL,OUTPUT_STALL);
 $finish;
end
initial begin #100000000; $fatal(1,"Testbench timeout"); end
endmodule
