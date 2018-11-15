set VERSION "1.0.1"
if { $argc == 0 } {
	puts "MTA configure file Encode/Decode rev.$VERSION"
	puts "Usage:tclsh mta_conf.tcl input_file \[option\]"
	puts "option:"
	puts "\[General\]"
	puts "-e        Encode a MTA configuration file"
	puts "-d        Decode a MTA configuration file"
	puts "-m        Use MD5 as config file hash signature (default is SHA1)"
	puts "-hash     Add config hash (non (default), na, eu)"
	puts "-out      Specify a output filename (for encode use)"
	puts "ex.tclsh mta_conf.tcl mta.txt -e -hash eu"
	exit
}
set input_file [file normalize [lindex $argv 0]]
if { ![file exist $input_file] } {
	puts "$input_file not available!"
	exit
}
set optionlist [list "-e" "-out" "-d" "-hash" "-m"]
set options [lrange $argv 1 end]
foreach op $options {
	if { [regexp {^-\w+$} $op] } {
		if { [lsearch $optionlist $op] == -1 } {
			puts "No such option \"$op\""
			exit
		}
	}
}
if { [lsearch $options "-e"] != -1 && [lsearch $options "-d"] != -1 } {
	puts "Cannot Encode/Decode at the same time!"
	exit
}
if { [lsearch $options "-out"] != -1 } {
	set filename [file normalize [lindex $options [expr [lsearch $options "-out"]+1]]]
} else {
	if { [lsearch $options "-e"] != -1 } {
		set filename "[file rootname $input_file].bin"
	} elseif { [lsearch $options "-d"] != -1 } {
		set filename "[file rootname $input_file].txt"
	}
}
set hash_type "non"
if { [lsearch $options "-hash"] != -1 } {
	set hash_type [lindex $options [expr [lsearch $options "-hash"]+1]]
	if { [lsearch [list "non" "na" "eu"] $hash_type] == -1 } {
		puts "hash type $hash_type not available!"
		exit
	}
}
if { [lsearch $options "-e"] != -1 && $hash_type != "non" } {
	if { [lsearch $options "-m"] != -1 } {
		set sig_type "md5"
	} else {
		set sig_type "sha1"
	}
}
proc enc_oid { oid } {
	set bits [split [string trimleft $oid "."] "."]
	set tmp [format "%02X" [expr 40*[lindex $bits 0]+[lindex $bits 1]]]
	foreach bit [lrange $bits 2 end] {
		if { $bit > 127 } {
			set s $bit
			set sl [list]
			set b 0
			while { $s > 127 } {
				set m [expr $s%128]
				set s [expr $s/128]
				if { $b == 0 } {
					set sl [format "%02X" $m]
				} else {
					set sl [linsert $sl 0 [format "%02X" [expr $m | 0x80]]]
				}
				incr b
			}
			set sl [linsert $sl 0 [format "%02X" [expr $s | 0x80]]]
			append tmp [join $sl ""]
		} else {
			append tmp [format "%02X" $bit]
		}
	}
	return $tmp
}
proc enc_hexstring { value } {
	binary scan $value c* sl
	set tmp ""
	foreach s $sl {
		append tmp [format "%02X" $s]
	}
	return $tmp
}
proc enc_ui32 { value } {
	if { $value > 127 } {
		return [format "%04X" $value]
	} else {
		return [format "%02X" $value]
	}
}
proc enc_int { value } {
	if { [regexp {^\-} $value] } {
		set tmp [string range [enc_hexstring [binary format I $value]] end-7 end]
	} else {
		set tmp [format "%02X" $value]
		if { [string length $tmp]%2 != 0 } {
			set tmp "0$tmp"
		}
	}
	return $tmp
}
proc enc_ip { value } {
	set ipl [split $value "."]
	set tmp ""
	foreach ip $ipl {
		append tmp [format "%02X" $ip]
	}
	return $tmp
}
proc add_tlv11 { oid value type } {
	set tmp ""
	set eoid [enc_oid $oid]
	set ol [format "%02X" [expr [string length $eoid]/2]]
	switch -- $type {
		"int" {
			set evalue [enc_int $value]
			set vt "02"
		}
		"bitstring" {
			set evalue [enc_hexstring [binary format b* [string trimleft $value "0"]]]
			set vt "03"
		}
		"string" {
			set evalue [enc_hexstring $value]
			set vt "04"
		}
		"null" {
			set evalue [enc_hexstring $value]
			set vt "05"
		}
		"OID" {
			set evalue [enc_oid $value]
			set vt "06"
		}
		"ipaddr" {
			set evalue [enc_ip $value]
			set vt "40"
		}
		"counter" {
			set evalue [enc_int $value]
			set vt "41"
		}
		"unsigned32" {
			set evalue [enc_ui32 $value]
			set vt "42"
		}
		"timeticks" {
			set evalue [enc_int $value]
			set vt "43"
		}
		"octetstring" {
			set evalue $value
			set vt "04"
		}
	}
	set vl [format "%02X" [expr [string length $evalue]/2]]
	set tmp "06$ol$eoid$vt$vl$evalue"
	set tl [format "%02X" [expr [string length $tmp]/2]]
	set tmp "30$tl$tmp"
	set tl [format "%02X" [expr [string length $tmp]/2]]
	return "0B$tl$tmp"
}
proc tobyte { str } {
	set tmp [list]
	set i 0
	set max [string length $str]
	while { $i < $max } {
		lappend tmp [string range $str $i [expr $i+1]]
		incr i 2
	}
	return $tmp
}
proc dec_oid { value } {
	set oid "."
	set bits [tobyte $value]
	append oid [expr 0x[lindex $bits 0]/40]
	append oid ".[expr 0x[lindex $bits 0]%40]"
	set otmp 0
	foreach bit [lrange $bits 1 end] {
		set b [expr 0x$bit]
		if { $b < 128 } {
			append oid ".[expr $otmp*0x80 + $b]"
			set otmp 0
		} else {
			set otmp [expr $otmp*0x80+($b & ~0x80)]
		}
	}
	return $oid
}
proc dec_conf { src {dst "" } } {
	set fd [open $src r]
	fconfigure $fd -translation binary
	set raw [read $fd [file size $src]]
	close $fd
	binary scan $raw "H*" raw
	set raw [string toupper [string range $raw 6 end-6]]
	set fd [open $dst w]
	while { $raw!= "" } {
		set tlvtmp [list ""]
		set i 2
		set tl [format "%d" 0x[string range $raw $i 3]]
		incr i 2
		set tmp [string range $raw $i [expr $i+2*$tl-1]]
		incr i [expr 2*$tl]
		set tmp [string range $tmp 4 end]
		set ol [format "%d" 0x[string range $tmp 2 3]]
		set ind 4
		set eoid [string range $tmp $ind [expr $ind+2*$ol-1]]
		incr ind [expr 2*$ol]
		set oid [dec_oid $eoid]
		lappend tlvtmp $oid
		set vt [string range $tmp $ind [expr $ind+1]]
		incr ind 2
		set vl [format "%d" 0x[string range $tmp $ind [expr $ind+1]]]
		incr ind 2
		set ev [string range $tmp $ind [expr $ind+$vl*2-1]]
		incr ind [expr 2*$vl]
		switch -- $vt {
			"02" {
				set type "int"
				set value [format %d 0x$ev]
			}
			"03" {
				set type "bitstring"
				binary scan [binary format H* $ev] B* value
			}
			"05" {
				set type "null"
				set value ""
			}
			"06" {
				set type "OID"
				set value [dec_oid $ev]
			}
			"40" {
				set type "ipaddr"
				set ipb [tobyte $ev]
				set ipl [list]
				foreach ip $ipb {
					lappend ipl [format "%d" 0x$ip]
				}
				set value [join $ipl "."]
			}
			"41" {
				set type "counter"
				set value [format %d 0x$ev]
			}
			"42" {
				set type "unsigned32"
				set value [format %d 0x$ev]
			}
			"43" {
				set type "timeticks"
				set value [format %d 0x$ev]
			}
			default {
				set v [binary format H* $ev]
				if { [regexp "\[\[:print:\]\]\{$vl\}" $v] } {
					set type "string"
					set value $v
				} else {
					set type "octetstring"
					set value $ev
				}
			}
		}
		lappend tlvtmp $value $type ""
		puts $fd [join $tlvtmp "\t"]
		set raw [string range $raw $i end]
	}
	close $fd
}
if { [lsearch $options "-e"] != -1 } {
	set hexstring "FE0101"
	set fd [open $input_file r]
	while { ![eof $fd] } {
		gets $fd line
		if { [string trim $line] == "" } { continue }
		set clist [split $line "\t"]
		if { [llength $clist] == 5 } {
			set mibname [lindex $clist 0]
			set oid [lindex $clist 1]
			set value [lindex $clist 2]
			set type [lindex $clist 3]
			set comment [lindex $clist 4]
		} else {
			puts "\[ERROR\] Incorrect source MTA config file format!"
			close $fd
			exit
		}
		if { $oid == ".1.3.6.1.4.1.7432.1.1.2.9.0" } { continue }
		if { $oid == ".1.3.6.1.4.1.4491.2.2.1.1.2.7.0" } { continue }
		set htlv [add_tlv11 $oid $value $type]
		append hexstring $htlv
	}
	close $fd
	if { $hexstring == "FE0101" } {
		puts "\[ERROR\] Could not find any MTA config setting in the file!"
		exit
	}
	set before_hash $hexstring
	append hexstring "FE01FF"
	set BStr [binary format H* $hexstring]
	if { $sig_type == "sha1" } {
		package require sha1
		set hash [string toupper [::sha1::sha1 -hex $BStr]]
	} else {
		package require md5
		set hash [string toupper [::md5::md5 -hex $BStr]]
	}
	switch -- $hash_type {
		"na" {
			append before_hash [add_tlv11 ".1.3.6.1.4.1.4491.2.2.1.1.2.7.0" $hash "octetstring"]
		}
		"eu" {
			append before_hash [add_tlv11 ".1.3.6.1.4.1.7432.1.1.2.9.0" $hash "octetstring"]
		}
	}
	append before_hash "FE01FF"
	set BStr [binary format H* $before_hash]
	set fd [open $filename w]
	fconfigure $fd -translation binary
	puts -nonewline $fd $BStr
	close $fd
} elseif { [lsearch $options "-d"] != -1 } {
	dec_conf $input_file $filename
}
