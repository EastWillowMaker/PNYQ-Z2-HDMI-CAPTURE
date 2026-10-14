library ieee;
use ieee.std_logic_1164.all;
use std.env.all;

entity sync_base_reset_tb is end;
architecture test of sync_base_reset_tb is
    signal source_clk, dest_clk : std_logic := '0';
    signal reset_async : std_logic := '1';
    signal reset_source, reset_dest : std_logic;
    signal out_zero, out_one, reverse_zero, reverse_one : std_logic;
    procedure source_edge(signal clk : inout std_logic) is
    begin
        wait for 2 ns; clk <= '1'; wait for 1 ns;
        clk <= '0'; wait for 2 ns;
    end;
    procedure dest_edge(signal clk : inout std_logic) is
    begin
        wait for 19 ns; clk <= '1'; wait for 1 ns;
        clk <= '0'; wait for 20 ns;
    end;
begin
    source_reset_bridge: entity work.ResetBridge generic map(kPolarity => '1')
        port map(aRst => reset_async, OutClk => source_clk, oRst => reset_source);
    dest_reset_bridge: entity work.ResetBridge generic map(kPolarity => '1')
        port map(aRst => reset_async, OutClk => dest_clk, oRst => reset_dest);
    zero_reset: entity work.SyncBase generic map(kResetTo => '0', kStages => 2)
        port map(aReset => reset_dest, iReset => reset_source, InClk => source_clk, iIn => '1',
                 OutClk => dest_clk, oOut => out_zero);
    one_reset: entity work.SyncBase generic map(kResetTo => '1', kStages => 2)
        port map(aReset => reset_dest, iReset => reset_source, InClk => source_clk, iIn => '0',
                 OutClk => dest_clk, oOut => out_one);
    reverse_zero_reset: entity work.SyncBase generic map(kResetTo => '0', kStages => 2)
        port map(aReset => reset_source, iReset => reset_dest, InClk => dest_clk,
                 iIn => '1', OutClk => source_clk, oOut => reverse_zero);
    reverse_one_reset: entity work.SyncBase generic map(kResetTo => '1', kStages => 2)
        port map(aReset => reset_source, iReset => reset_dest, InClk => dest_clk,
                 iIn => '0', OutClk => source_clk, oOut => reverse_one);
    process
    begin
        wait for 10 ns;
        assert out_zero = '0' and out_one = '1' report "Startup reset failed" severity failure;
        reset_async <= '0'; wait for 1 ns;
        source_edge(source_clk);
        for i in 1 to 4 loop dest_edge(dest_clk); end loop;
        assert out_zero = '0' and out_one = '1'
            report "Source data escaped before source reset qualification" severity failure;
        source_edge(source_clk); source_edge(source_clk);
        dest_edge(dest_clk); dest_edge(dest_clk);
        assert out_zero = '1' and out_one = '0'
            report "Qualified source data did not cross after destination synchronizer" severity failure;
        source_edge(source_clk); source_edge(source_clk);
        assert reverse_zero = '1' and reverse_one = '0'
            report "Reverse crossing qualification failed" severity failure;
        reset_async <= '1'; wait for 1 ns;
        assert out_zero = '0' and out_one = '1'
            report "Stopped clocks prevented asynchronous reset assertion" severity failure;
        reset_async <= '0'; wait for 1 ns;
        source_edge(source_clk); reset_async <= '1'; wait for 1 ns;
        reset_async <= '0'; wait for 1 ns;
        source_edge(source_clk);
        for i in 1 to 4 loop dest_edge(dest_clk); end loop;
        assert out_zero = '0' and out_one = '1'
            report "Reset chatter bypassed source reset qualification" severity failure;
        source_edge(source_clk); source_edge(source_clk);
        dest_edge(dest_clk); dest_edge(dest_clk);
        assert out_zero = '1' and out_one = '0' report "Chatter recovery failed" severity failure;
        source_edge(source_clk); source_edge(source_clk);
        assert reverse_zero = '1' and reverse_one = '0'
            report "Reverse crossing recovery failed" severity failure;
        report "SyncBase: both polarities, source/destination qualification, stopped-clock assertion, chatter PASS";
        finish;
    end process;
end;
