-- This Source Code Form is subject to the terms of the Mozilla Public
-- License, v. 2.0. If a copy of the MPL was not distributed with this file,
-- You can obtain one at http://mozilla.org/MPL/2.0/.
--
-- Copyright (c) 2014, Lars Asplund lars.anders.asplund@gmail.com

library vunit_lib;
context vunit_lib.vunit_context;

use work.message_pkg.all;

entity tb_message_passing is
  generic (runner_cfg : runner_cfg_t);
end entity;

architecture tb of tb_message_passing is
  signal start_other_actor_process : boolean := false;
  signal start_other_actor_process_with_sensitivity_list : boolean := false;
  signal clk : boolean := false;
begin
  main : process
    variable actor, other_actor : actor_t;
  begin
    test_runner_setup(runner, runner_cfg);
    while test_suite loop
      if run("test_create_actor") then
        actor := create_actor("actor");
        other_actor := create_actor("other_actor");
        assert actor /= other_actor;

      elsif run("test_send_message") then
        actor := create_actor("actor");
        other_actor := create_actor("other_actor");
        send_message(other_actor, actor, "hello world");
        notify(net);
        assert not has_messages(other_actor);
        assert has_messages(actor);
        assert message_sender(actor) = other_actor;
        assert message_data(actor) = "hello world";
        pop_message(actor);
        assert not has_messages(actor);

      elsif run("test_send_message_to_other_process") then
        actor := create_actor("actor");
        start_other_actor_process <= true;
        wait for 1 ns;
        other_actor := lookup_actor("actor_other_process");
        send_message(actor, other_actor, "hello world");
        notify(net);
        wait_for_messages(actor, net);
        assert message_sender(actor) = other_actor;
        assert message_data(actor) = "answer";

      elsif run("test_send_message_to_other_process_with_sensitivity_list") then
        actor := create_actor("actor");
        start_other_actor_process_with_sensitivity_list <= true;
        wait for 4 ns;
        other_actor := lookup_actor("actor_other_process");
        send_message(actor, other_actor, "hello world");
        notify(net);
        wait_for_messages(actor, net);
        assert message_sender(actor) = other_actor;
        assert message_data(actor) = "answer";
      end if;
    end loop;
    test_runner_cleanup(runner);
  end process;

  other_actor_process : process
    variable actor : actor_t;
  begin
    wait until start_other_actor_process;
    actor := create_actor("actor_other_process");
    assert not has_messages(actor);
    wait_for_messages(actor, net);
    assert has_messages(actor);
    send_message(actor, message_sender(actor), "answer");
    notify(net);
    wait;
  end process;

  other_actor_process_with_sensitivity_list : process (clk)
    variable actor : actor_t;
    variable initialized : boolean := false;
  begin
    if rising_edge(clk) then
      if not initialized then
        if start_other_actor_process_with_sensitivity_list then
          actor := create_actor("actor_other_process");
          initialized := true;
        end if;
      else
        if has_messages(actor) then
          send_message(actor, message_sender(actor), "answer");
          notify(net);
          pop_message(actor);
        end if;
      end if;
    end if;
  end process;

  test_runner_watchdog(runner, 1 ms);


  clk <= not clk after 1 ns;
end architecture;
