use std.textio.all;

package message_pkg is

  subtype actor_t is integer;
  impure function create_actor(name : string) return actor_t;
  impure function lookup_actor(name : string) return actor_t;

  type string_ptr_t is access string;
  type message_t is record
    from_actor : actor_t;
    data : string_ptr_t;
  end record;

  type i64_t is record
    low : integer;
    high : integer;
  end record;

  constant i64_zero : i64_t := (low => integer'left, high => integer'left);

  function inc(value : i64_t) return i64_t;
  function max(v1, v2 : i64_t) return i64_t;

  type unetwork_t is record
    event_count : i64_t;
  end record;

  type unetwork_vec_t is array (integer range <>) of unetwork_t;

  constant idle_network : unetwork_t := (event_count => i64_zero);

  function resolved(networks : unetwork_vec_t) return unetwork_t;
  subtype network_t is resolved unetwork_t;

  signal net : network_t := idle_network;

  procedure send_message(self : actor_t;
                         actor : actor_t;
                         data : string);

  procedure notify(signal net : inout network_t);

  procedure wait_for_messages(self : actor_t; signal net : inout network_t);
  impure function has_messages(self : actor_t) return boolean;
  impure function message_sender(self : actor_t) return actor_t;
  impure function message_data(self : actor_t) return string;
  procedure pop_message(self : actor_t);

  procedure print_network_state;
end package;

package body message_pkg is
  function resolved(networks : unetwork_vec_t) return unetwork_t is
    variable event_count : i64_t := i64_zero;
  begin
    for i in networks'range loop
      event_count := max(networks(i).event_count, event_count);
    end loop;
    return (event_count => event_count);
  end function;

  function inc(value : i64_t) return i64_t is
  begin
    if value.low = integer'right then
      return (low => integer'left,
              high => value.high + 1);
      -- Assume high will never wrap and that this function is not called 2**64
      -- times
    else
      return (low => value.low + 1,
              high => value.high);
    end if;
  end function;

  function max(v1, v2 : i64_t) return i64_t is
  begin
    if v1.high > v2.high then
      return v1;
    elsif v1.high < v2.high then
      return v2;
    elsif v1.low < v2.low then
      return v2;
    else
      return v1;
    end if;
  end function;

  type message_node_t;
  type message_node_ptr_t is access message_node_t;

  type message_node_t is record
    message : message_t;
    next_node : message_node_ptr_t;
  end record;

  type actor_node_t is record
    actor : actor_t;
    name : string_ptr_t;
    num_messages : natural;
    first_message : message_node_ptr_t;
    last_message : message_node_ptr_t;
  end record;

  type actor_node_vec_t is array (integer range <>) of actor_node_t;
  type actor_node_vec_ptr_t is access actor_node_vec_t;

  impure function null_actor_node return actor_node_t is
  begin
    return (actor => 0,
            name => null,
            num_messages => 0,
            first_message => null,
            last_message => null);
  end function;

  impure function new_actor_node(actor : actor_t; name : string) return actor_node_t is
  begin
    return (actor => actor,
            name => new string'(name),
            num_messages => 0,
            first_message => null,
            last_message => null);
  end function;

  impure function new_message(from_actor : actor_t; data : string) return message_t is
  begin
    return (from_actor => from_actor,
            data => new string'(data));
  end function;

  procedure deallocate(variable message : inout message_t) is
  begin
    deallocate(message.data);
  end procedure;

  type network_state_t is protected
    impure function create_actor(name : string) return actor_t;
    impure function lookup_actor(name : string) return actor_t;
    procedure send_message(from_actor, to_actor : actor_t; data : string);
    impure function has_messages(actor : actor_t) return boolean;
    -- Work-arround that VHDL cannot return pointers from protected types
    impure function first_message_from_actor(actor : actor_t) return actor_t;
    impure function first_message_data(actor : actor_t) return string;
    procedure pop_message(actor : actor_t);
    procedure pretty_print;
    impure function event_count return i64_t;
  end protected;

  type network_state_t is protected body
    variable actors : actor_node_vec_ptr_t := null;
    variable my_event_count : i64_t := i64_zero;

    impure function num_actors return natural is
    begin
      if actors = null then
        return 0;
      else
        return actors'length;
      end if;
    end function;

    impure function create_actor(name : string) return actor_t is
      variable new_actors : actor_node_vec_ptr_t;
    begin
      -- @TODO test error detection when multiple actors with same name is created
      if actors = null then
        actors := new actor_node_vec_t'(0 => null_actor_node);
      else
        new_actors := new actor_node_vec_t'(0 to actors'length => null_actor_node);
        for i in 0 to actors'length-1 loop
          new_actors(i) := actors(i);
        end loop;
        deallocate(actors);
        actors := new_actors;
      end if;
      actors(actors'length-1) := new_actor_node(actors'length-1, name);
      return actors(actors'length-1).actor;
    end function;

    impure function lookup_actor(name : string) return actor_t is
    begin
      for i in 0 to num_actors-1 loop
        if actors(i).name.all = name then
          return actors(i).actor;
        end if;
      end loop;
      assert false;
      return 0;
    end function;

    impure function event_count return i64_t is
    begin
      return my_event_count;
    end function;

    procedure send_message(from_actor, to_actor : actor_t; data : string) is
      variable message_node : message_node_ptr_t;
    begin
      my_event_count := inc(my_event_count);
      message_node := new message_node_t'(
        message => new_message(from_actor, data),
        next_node => null);

      actors(to_actor).num_messages := actors(to_actor).num_messages + 1;
      if actors(to_actor).first_message = null then
        actors(to_actor).first_message := message_node;
      else
        actors(to_actor).last_message.next_node := message_node;
      end if;

      actors(to_actor).last_message := message_node;
    end procedure;

    impure function has_messages(actor : actor_t) return boolean is
    begin
      return actors(actor).first_message /= null;
    end function;

    impure function first_message_from_actor(actor : actor_t) return actor_t is
    begin
      return actors(actor).first_message.message.from_actor;
    end function;

    impure function first_message_data(actor : actor_t) return string is
    begin
      return actors(actor).first_message.message.data.all;
    end function;

    procedure pop_message(actor : actor_t) is
      variable tmp : message_node_ptr_t;
    begin
      tmp := actors(actor).first_message;
      actors(actor).first_message := actors(actor).first_message.next_node;
      actors(actor).num_messages := actors(actor).num_messages - 1;
      -- @TODO move to method
      deallocate(tmp.message);
      deallocate(tmp);
    end procedure;

    procedure pretty_print is
      variable ptr : message_node_ptr_t;
      variable count : natural := 0;
    begin
      write(output, "Network state at time " & time'image(now) & LF);
      write(output, "  Number of actors: " & integer'image(num_actors) & LF);
      write(output, "" & LF);
      for i in 0 to num_actors-1 loop
        write(output, "  Actor " & integer'image(i+1) & " of " & integer'image(num_actors) & ":" & LF);
        write(output, "    name: " & actors(i).name.all & LF);
        write(output, "    num messages: " & integer'image(actors(i).num_messages) & LF);
        ptr := actors(i).first_message;
        count := 0;
        while ptr /= null loop
          write(output, "    message " & integer'image(count+1) & " of " & integer'image(actors(i).num_messages) & LF);
          write(output, "      from_actor: " & actors(ptr.message.from_actor).name.all & LF);
          write(output, "      data: " & ptr.message.data.all & LF);
          ptr := ptr.next_node;
          count := count + 1;
        end loop;
        write(output, "" & LF);
      end loop;
    end procedure;


  end protected body;

  shared variable network_state : network_state_t;

  impure function create_actor(name : string) return actor_t is
  begin
    return network_state.create_actor(name);
  end function;

  impure function lookup_actor(name : string) return actor_t is
  begin
    return network_state.lookup_actor(name);
  end function;

  procedure notify(signal net : inout network_t) is
  begin
    net.event_count <= network_state.event_count;
  end procedure;

  procedure send_message(self : actor_t;
                         actor : actor_t;
                         data : string) is
  begin
    network_state.send_message(from_actor => self,
                               to_actor => actor,
                               data => data);
  end procedure;

  procedure wait_for_messages(self : actor_t; signal net : inout network_t) is
    variable next_count : i64_t;
  begin
    while not has_messages(self) loop
      next_count := inc(network_state.event_count);
      wait until net.event_count = next_count;
    end loop;
  end procedure;

  impure function has_messages(self : actor_t) return boolean is
  begin
    return network_state.has_messages(self);
  end function;

  impure function message_sender(self : actor_t) return actor_t is
  begin
    return network_state.first_message_from_actor(self);
  end function;

  impure function message_data(self : actor_t) return string is
  begin
    return network_state.first_message_data(self);
  end function;

  procedure pop_message(self : actor_t) is
  begin
    network_state.pop_message(self);
  end procedure;

  procedure print_network_state is
  begin
    network_state.pretty_print;
  end procedure;
end package body;
