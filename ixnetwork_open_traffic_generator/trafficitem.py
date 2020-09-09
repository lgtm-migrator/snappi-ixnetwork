import json
from ixnetwork_open_traffic_generator.customfield import CustomField

class TrafficItem(CustomField):
    """TrafficItem configuration

    Args
    ----
    - ixnetworkapi (IxNetworkApi): instance of the ixnetworkapi class
    
    """
    _STACK_IGNORE = [
        'ethernet.fcs'
    ]

    _TYPE_TO_HEADER = {
        'ethernet': 'ethernet',
        'pfcPause': 'pfc_pause',
        'vlan': 'vlan',
        'ipv4': 'ipv4',
        'custom': 'custom'
    }

    _HEADER_TO_TYPE = {
        'ethernet': 'ethernet',
        'pfcpause': 'pfcPause',
        'vlan': 'vlan',
        'ipv4': 'ipv4',
        'custom': 'custom'
    }

    _BIT_RATE_UNITS_TYPE = {
        'bps' : 'bitsPerSec',
        'kbps' : 'kbitsPerSec',
        'mbps' : 'mbitsPerSec',
        'gbps' : 'mbytesPerSec'
    }
    
    _PFCPAUSE = {
        'dst': 'pfcPause.header.header.dstAddress',
        'src': 'pfcPause.header.header.srcAddress',
        'ether_type': 'pfcPause.header.header.ethertype',
        'control_op_code': 'pfcPause.header.macControl.controlOpcode',
        'class_enable_vector': 'pfcPause.header.macControl.priorityEnableVector',
        'pause_class_0': 'pfcPause.header.macControl.pauseQuanta.pfcQueue0',
        'pause_class_1': 'pfcPause.header.macControl.pauseQuanta.pfcQueue1',
        'pause_class_2': 'pfcPause.header.macControl.pauseQuanta.pfcQueue2',
        'pause_class_3': 'pfcPause.header.macControl.pauseQuanta.pfcQueue3',
        'pause_class_4': 'pfcPause.header.macControl.pauseQuanta.pfcQueue4',
        'pause_class_5': 'pfcPause.header.macControl.pauseQuanta.pfcQueue5',
        'pause_class_6': 'pfcPause.header.macControl.pauseQuanta.pfcQueue6',
        'pause_class_7': 'pfcPause.header.macControl.pauseQuanta.pfcQueue7',
    }

    _ETHERNET = {
        'dst': 'ethernet.header.destinationAddress',
        'src': 'ethernet.header.sourceAddress',
        'ether_type': 'ethernet.header.etherType',
        'pfc_queue': 'ethernet.header.pfcQueue',
    }

    _VLAN = {
        'id': 'vlan.header.vlanTag.vlanID',
        'cfi': 'vlan.header.vlanTag.cfi',
        'priority': 'vlan.header.vlanTag.vlanUserPriority',
        'protocol': 'vlan.header.protocolID'
    }

    _IPV4 = {
        'src' : 'ipv4.header.srcIp',
        'dst' : 'ipv4.header.dstIp',
        'priority' : '_ipv4_priority',
    }

    def __init__(self, ixnetworkapi):
        self._api = ixnetworkapi
        
    def config(self):
        """Configure config.flows onto Ixnetwork.Traffic.TrafficItem
        
        CRUD
        ----
        - DELETE any TrafficItem.Name that does not exist in config.flows
        - CREATE TrafficItem for any config.flows[*].name that does not exist
        - UPDATE TrafficItem for any config.flows[*].name that exists
        """
        ixn_traffic_item = self._api._traffic_item
        for traffic_item in ixn_traffic_item.find():
            if self.find_item(self._config.flows, 'name', traffic_item.Name) is None:
                traffic_item.remove()

        if self._api.config.flows is not None:
            for flow in self._api.config.flows:
                args = {
                    'Name': flow.name,
                    'TrafficItemType': 'l2L3'
                }
                if flow.endpoint is None:
                    raise ValueError('%s endpoint cannot be None' % flow.name)
                elif flow.endpoint.choice == 'port':
                    args['TrafficType'] = 'raw'
                elif flow.endpoint.device.packet_encap in ['ethernet', 'vlan']:
                    args['TrafficType'] = 'ethernetVlan'
                else:
                    args['TrafficType'] = flow.endpoint.device.packet_encap
                ixn_traffic_item.find(Name=flow.name)
                if len(ixn_traffic_item) == 0:
                    ixn_traffic_item.add(**args)
                else:
                    ixn_traffic_item.update(**args)
                self._configure_endpoint(ixn_traffic_item.EndpointSet, flow.endpoint)
                if flow.enable is not None:
                    ixn_traffic_item.Enabled = flow.enable
                ixn_stream = ixn_traffic_item.ConfigElement.find()
                self._configure_stack(ixn_stream, flow.packet)
                self._configure_size(ixn_stream, flow.size)
                self._configure_rate(ixn_stream, flow.rate)
                self._configure_tx_control(ixn_stream, flow.duration)

    def _configure_endpoint(self, ixn_endpoint_set, endpoint):
        """Transform flow.endpoint to /trafficItem/endpointSet
        The model allows for only one endpoint per traffic item
        """
        args = {
            'Sources': [],
            'Destinations' : []
        }
        if (endpoint.choice == "port"):
            args['Sources'].append(self._api.get_ixn_object(endpoint.port.tx_port_name).Protocols.find())
            for port_name in endpoint.port.rx_port_names:
                args['Destinations'].append(self._api.get_ixn_object(port_name).Protocols.find())
            ixn_endpoint_set.add(**args)
        else:
            for port_name in endpoint.device.tx_device_names:
                args['Sources'].append(self._api.get_ixn_object(port_name))
            for port_name in endpoint.device.rx_device_names:
                args['Destinations'].append(self._api.get_ixn_object(port_name))
            ixn_endpoint_set.add(**args)

    def _configure_stack(self, ixn_stream, headers):
        """Transform flow.packets[0..n] to /traffic/trafficItem/configElement/stack 
        The len of the headers list is the definitive list which means add/remove
        any stack items so that the stack list matches the headers list.
        If the headers list is empty then use the traffic generator default stack.
        """
        stacks_to_remove = []
        ixn_stack = ixn_stream.Stack.find()
        for i in range(0, len(headers)):
            header = headers[i]
            if len(ixn_stack) <= i:
                stack = self._add_stack(ixn_stream, stack, header)
            else:
                stack_type_id = ixn_stack[i].StackTypeId
                if stack_type_id in self._STACK_IGNORE:
                    stack = self._add_stack(ixn_stream, stack, header)
                elif stack_type_id not in TrafficItem._TYPE_TO_HEADER:
                    stacks_to_remove.append(ixn_stack[i])
                    stack = self._add_stack(ixn_stream, ixn_stack[i], header)
                elif TrafficItem._TYPE_TO_HEADER[stack_type_id] != header.choice:
                    stacks_to_remove.append(ixn_stack[i])
                    stack = self._add_stack(ixn_stream, ixn_stack[i], header)
                else:
                    stack = ixn_stack[i]
            self._configure_field(stack.Field, header)
        for stack in stacks_to_remove:
            stack.Remove()
    
    def _add_stack(self, ixn_stream, ixn_stack, header):
        type_id = '^%s$' % TrafficItem._HEADER_TO_TYPE[header.choice]
        template = self._api._traffic.ProtocolTemplate.find(StackTypeId=type_id)
        stack_href = ixn_stack.AppendProtocol(template)
        return ixn_stream.Stack.read(stack_href)

    def _configure_field(self, ixn_field, header):
        """Transform flow.packets[0..n].header.choice to /traffic/trafficItem/configElement/stack/field
        """
        field_map = getattr(self, '_%s' % header.choice.upper())
        packet = getattr(header, header.choice)
        for packet_field_name in dir(packet):
            if packet_field_name in field_map:
                pattern = getattr(packet, packet_field_name)
                field_type_id = field_map[packet_field_name]
                self._configure_pattern(ixn_field, field_type_id, pattern)

    def _configure_pattern(self, ixn_field, field_type_id, pattern):
        if pattern == None:
            return
        
        custom_field = getattr(self, field_type_id, None)
        if custom_field is not None:
            custom_field(ixn_field, pattern)
            return

        ixn_field = ixn_field.find(FieldTypeId=field_type_id)
        if pattern.choice == 'fixed':
            ixn_field.update(Auto=False, ValueType='singleValue', SingleValue=pattern.fixed)
        elif pattern.choice == 'list':
            ixn_field.update(Auto=False, ValueType='valueList', ValueList=pattern.list)
        elif pattern.choice == 'counter':
            value_type = 'increment' if pattern.counter.up is True else 'decrement'
            ixn_field.update(Auto=False, 
                ValueType=value_type, 
                StartValue=pattern.counter.start,
                StepValue=pattern.counter.step,
                CountValue=pattern.counter.count)
        elif pattern.choice == 'random':
            ixn_field.update(Auto=False, 
                ValueType='repeatableRandomRange', 
                MinValue=pattern.random.min,
                MaxValue=pattern.random.max,
                StepValue=pattern.random.step,
                Seed=pattern.random.seed,
                CountValue=pattern.random.count)
        else:
            # TBD: add to set_config errors - invalid pattern specified
            pass
            
        if pattern.group_by is not None:
            ixn_field.TrackingEnabled = True
            self._api.ixn_objects[pattern.group_by] = ixn_field.href
    
    def _configure_size(self, ixn_stream, size):
        """ Transform frameSize flows.size to /traffic/trafficItem[*]/configElement[*]/frameSize
        """
        if size is None:
            return
        ixn_frame_size = ixn_stream.FrameSize
        if size.choice == 'fixed':
            ixn_frame_size.Type = "fixed"
            ixn_frame_size.FixedSize = size.fixed
        elif size.choice == 'increment':
            ixn_frame_size.Type = "increment"
            ixn_frame_size.IncrementFrom = size.increment.start
            ixn_frame_size.IncrementTo = size.increment.end
            ixn_frame_size.IncrementStep = size.increment.step
        elif size.choice == 'random':
            ixn_frame_size.Type = "random"
            ixn_frame_size.RandomMin = size.random.min
            ixn_frame_size.RandomMax = size.random.max
        else:
            print('Warning - We need to implement this %s choice' %size.choice)
            
    def _configure_rate(self, ixn_stream, rate):
        """ Transform frameRate flows.rate to /traffic/trafficItem[*]/configElement[*]/frameRate
        """
        if rate is None:
            return
        ixn_frame_rate = ixn_stream.FrameRate
        if rate.unit == 'line':
            ixn_frame_rate.Type = 'percentLineRate'
        elif rate.unit == 'pps':
            ixn_frame_rate.Type = 'framesPerSecond'
        else:
            ixn_frame_rate.Type = 'bitsPerSecond'
            ixn_frame_rate.BitRateUnitsType = TrafficItem._BIT_RATE_UNITS_TYPE[rate.unit]
        ixn_frame_rate.Rate = rate.value

    def _configure_tx_control(self, ixn_stream, duration):
        """Transform duration flows.duration to /traffic/trafficItem[*]/configElement[*]/TransmissionControl
        """
        if duration is None:
            return
        ixn_tx_control = ixn_stream.TransmissionControl
        if duration.choice == 'fixed':
            if duration.fixed.delay_unit not in ['bytes', 'nanoseconds', None]:
                raise ValueError('flow.duration.fixed.delay_unit is accepting [bytes, nanoseconds] Not %s'
                                 % duration.fixed.delay_unit);
            if duration.fixed.packets <= 0:
                ixn_tx_control.update(Type='continuous',
                    MinGapBytes=duration.fixed.gap,
                    StartDelay=duration.fixed.delay,
                    StartDelayUnits=duration.fixed.delay_unit)
            else:
                ixn_tx_control.update(Type='fixedFrameCount', 
                    FrameCount=duration.fixed.packets,
                    MinGapBytes=duration.fixed.gap,
                    StartDelay=duration.fixed.delay,
                    StartDelayUnits=duration.fixed.delay_unit)
        elif duration.choice == 'burst':
            enable_gap = False
            if (duration.burst.inter_burst_gap is not None or
                duration.burst.inter_burst_gap_unit is not None):
                enable_gap = True
            if duration.burst.inter_burst_gap_unit not in ['bytes', 'nanoseconds', None]:
                raise ValueError('flow.duration.fixed.inter_burst_gap_unit is accepting [bytes, nanoseconds] Not %s' % duration.fixed.delay_unit);
            ixn_tx_control.update(Type='custom',
                BurstPacketCount=duration.burst.packets,
                MinGapBytes=duration.burst.gap,
                EnableInterBurstGap=enable_gap,
                InterBurstGap=duration.burst.inter_burst_gap,
                InterBurstGapUnits=duration.burst.inter_burst_gap_unit)

    def transmit(self, request):
        """Set flow transmit
        """
        regex = None
        if request.names is not None and len(request.names) > 0:
            regex = '^(%s)$' % '|'.join(request.names)
        self._api._traffic.Generate()
        self._api._traffic.Apply()
        self._api._traffic_item.find(regex)
        if request.state == 'start':
            self._api._traffic_item.StartStatelessTraffic()
        elif request.state == 'stop':
            self._api._traffic_item.StopStatelessTraffic()
        elif request.state == 'pause':
            self._api._traffic_item.PauseStatelessTraffic(True)
        elif request.state == 'resume':
            self._api._traffic_item.PauseStatelessTraffic(False)

    def results(self, request):
        """Return flow results
        """
        return None
