using System;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;
using System.Threading;

// Assetto Corsa shared memory reader.
// Run this on the same Windows session as Assetto Corsa.
//
// Build/run with:
//   dotnet run

Console.Title = "Assetto Corsa Shared Memory Reader";

if (!OperatingSystem.IsWindows())
{
    Console.WriteLine("Assetto Corsa shared memory can only be read on Windows.");
    Console.WriteLine("This code is ready, but the current machine cannot open Local\\acpmf_* maps.");
    return;
}

Console.WriteLine("Waiting for Assetto Corsa shared memory...");
Console.WriteLine("Start a driving session in AC, then leave this window open.\n");
Console.CursorVisible = false;

using var physicsMap = OpenMapWhenReady("Local\\acpmf_physics");
using var graphicsMap = OpenMapWhenReady("Local\\acpmf_graphics");
using var staticMap = OpenMapWhenReady("Local\\acpmf_static");

using var physics = physicsMap.CreateViewAccessor(0, Marshal.SizeOf<PhysicsPage>(), MemoryMappedFileAccess.Read);
using var graphics = graphicsMap.CreateViewAccessor(0, Marshal.SizeOf<GraphicsPage>(), MemoryMappedFileAccess.Read);
using var statics = staticMap.CreateViewAccessor(0, Marshal.SizeOf<StaticPage>(), MemoryMappedFileAccess.Read);

var printedStaticInfo = false;

while (true)
{
    var p = ReadStruct<PhysicsPage>(physics);
    var g = ReadStruct<GraphicsPage>(graphics);
    var s = ReadStruct<StaticPage>(statics);

    if (!printedStaticInfo)
    {
        Console.WriteLine($"AC version : {s.AcVersion}");
        Console.WriteLine($"Car        : {s.CarModel}");
        Console.WriteLine($"Track      : {s.Track} {s.TrackConfiguration}".TrimEnd());
        Console.WriteLine($"Driver     : {s.PlayerName} {s.PlayerSurname}".TrimEnd());
        Console.WriteLine();
        printedStaticInfo = true;
    }

    Console.SetCursorPosition(0, 6);
    WriteDashboardLine($"Status     : {g.Status,-12} Session: {g.Session,-10} Lap: {g.CompletedLaps + 1}/{g.NumberOfLaps}");
    WriteDashboardLine($"Speed      : {p.SpeedKmh,7:0.0} km/h   RPM: {p.Rpms,6}   Gear: {FormatGear(p.Gear),2}");
    WriteDashboardLine($"Input      : Gas {p.Gas,5:P0}   Brake {p.Brake,5:P0}   Clutch {p.Clutch,5:P0}   Steer {p.SteerAngle,7:0.000}");
    WriteDashboardLine($"Fuel       : {p.Fuel,7:0.00} L   Est laps: {g.FuelEstimatedLaps,6:0.00}   Position: {g.Position}");
    WriteDashboardLine($"Lap time   : Current {g.CurrentTime,-12} Last {g.LastTime,-12} Best {g.BestTime,-12}");
    WriteDashboardLine($"Tyres C    : FL {p.TyreCoreTemperature[0],5:0.0}  FR {p.TyreCoreTemperature[1],5:0.0}  RL {p.TyreCoreTemperature[2],5:0.0}  RR {p.TyreCoreTemperature[3],5:0.0}");
    WriteDashboardLine($"Brake C    : FL {p.BrakeTemp[0],5:0.0}  FR {p.BrakeTemp[1],5:0.0}  RL {p.BrakeTemp[2],5:0.0}  RR {p.BrakeTemp[3],5:0.0}");
    WriteDashboardLine("Press Ctrl+C to stop.");

    Thread.Sleep(100);
}

static MemoryMappedFile OpenMapWhenReady(string name)
{
    while (true)
    {
        try
        {
            return MemoryMappedFile.OpenExisting(name, MemoryMappedFileRights.Read);
        }
        catch (FileNotFoundException)
        {
            Thread.Sleep(500);
        }
    }
}

static T ReadStruct<T>(MemoryMappedViewAccessor accessor) where T : struct
{
    var size = Marshal.SizeOf<T>();
    var bytes = new byte[size];
    accessor.ReadArray(0, bytes, 0, size);

    var handle = GCHandle.Alloc(bytes, GCHandleType.Pinned);
    try
    {
        return Marshal.PtrToStructure<T>(handle.AddrOfPinnedObject());
    }
    finally
    {
        handle.Free();
    }
}

static string FormatGear(int gear)
{
    return gear switch
    {
        0 => "R",
        1 => "N",
        _ => (gear - 1).ToString()
    };
}

static void WriteDashboardLine(string value)
{
    var width = Console.IsOutputRedirected ? value.Length : Math.Max(value.Length, Console.WindowWidth - 1);
    Console.WriteLine(value.PadRight(width));
}

[StructLayout(LayoutKind.Sequential, Pack = 4)]
public struct PhysicsPage
{
    public int PacketId;
    public float Gas;
    public float Brake;
    public float Fuel;
    public int Gear;
    public int Rpms;
    public float SteerAngle;
    public float SpeedKmh;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
    public float[] Velocity;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
    public float[] AccG;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] WheelSlip;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] WheelLoad;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] WheelsPressure;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] WheelAngularSpeed;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] TyreWear;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] TyreDirtyLevel;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] TyreCoreTemperature;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] CamberRad;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] SuspensionTravel;

    public float Drs;
    public float Tc;
    public float Heading;
    public float Pitch;
    public float Roll;
    public float CgHeight;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 5)]
    public float[] CarDamage;

    public int NumberOfTyresOut;
    public int PitLimiterOn;
    public float Abs;
    public float KersCharge;
    public float KersInput;
    public int AutoShifterOn;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 2)]
    public float[] RideHeight;

    public float TurboBoost;
    public float Ballast;
    public float AirDensity;
    public float AirTemp;
    public float RoadTemp;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
    public float[] LocalAngularVelocity;

    public float FinalForceFeedback;
    public float PerformanceMeter;
    public int EngineBrake;
    public int ErsRecoveryLevel;
    public int ErsPowerLevel;
    public int ErsHeatCharging;
    public int ErsIsCharging;
    public float KersCurrentKj;
    public int DrsAvailable;
    public int DrsEnabled;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] BrakeTemp;

    public float Clutch;
}

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode, Pack = 4)]
public struct GraphicsPage
{
    public int PacketId;
    public AcStatus Status;
    public AcSessionType Session;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 15)]
    public string CurrentTime;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 15)]
    public string LastTime;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 15)]
    public string BestTime;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 15)]
    public string Split;

    public int CompletedLaps;
    public int Position;
    public int ICurrentTime;
    public int ILastTime;
    public int IBestTime;
    public float SessionTimeLeft;
    public float DistanceTraveled;
    public int IsInPit;
    public int CurrentSectorIndex;
    public int LastSectorTime;
    public int NumberOfLaps;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string TyreCompound;

    public float ReplayTimeMultiplier;
    public float NormalizedCarPosition;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 3)]
    public float[] CarCoordinates;

    public float PenaltyTime;
    public AcFlagType Flag;
    public int IdealLineOn;
    public int IsInPitLane;
    public float SurfaceGrip;
    public int MandatoryPitDone;
    public float WindSpeed;
    public float WindDirection;
    public int IsSetupMenuVisible;
    public int MainDisplayIndex;
    public int SecondaryDisplayIndex;
    public int Tc;
    public int TcCut;
    public int EngineMap;
    public int Abs;
    public float FuelXLap;
    public int RainLights;
    public int FlashingLights;
    public int LightsStage;
    public float ExhaustTemperature;
    public int WiperLevel;
    public int DriverStintTotalTimeLeft;
    public int DriverStintTimeLeft;
    public int RainTyres;
    public int SessionIndex;
    public float UsedFuel;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 15)]
    public string DeltaLapTime;

    public int IDeltaLapTime;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 15)]
    public string EstimatedLapTime;

    public int IEstimatedLapTime;
    public int IsDeltaPositive;
    public int ISplit;
    public int IsValidLap;
    public float FuelEstimatedLaps;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string TrackStatus;
}

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode, Pack = 4)]
public struct StaticPage
{
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 15)]
    public string SmVersion;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 15)]
    public string AcVersion;

    public int NumberOfSessions;
    public int NumCars;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string CarModel;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string Track;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string PlayerName;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string PlayerSurname;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string PlayerNick;

    public int SectorCount;
    public float MaxTorque;
    public float MaxPower;
    public int MaxRpm;
    public float MaxFuel;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] SuspensionMaxTravel;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)]
    public float[] TyreRadius;

    public float MaxTurboBoost;
    public float Deprecated1;
    public float Deprecated2;
    public int PenaltiesEnabled;
    public float AidFuelRate;
    public float AidTireRate;
    public float AidMechanicalDamage;
    public int AidAllowTyreBlankets;
    public float AidStability;
    public int AidAutoClutch;
    public int AidAutoBlip;
    public int HasDrs;
    public int HasErs;
    public int HasKers;
    public float KersMaxJ;
    public int EngineBrakeSettingsCount;
    public int ErsPowerControllerCount;
    public float TrackSplineLength;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string TrackConfiguration;

    public float ErsMaxJ;
    public int IsTimedRace;
    public int HasExtraLap;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 33)]
    public string CarSkin;
}

public enum AcStatus
{
    Off = 0,
    Replay = 1,
    Live = 2,
    Pause = 3
}

public enum AcSessionType
{
    Practice = 0,
    Qualify = 1,
    Race = 2,
    Hotlap = 3,
    TimeAttack = 4,
    Drift = 5,
    Drag = 6
}

public enum AcFlagType
{
    NoFlag = 0,
    BlueFlag = 1,
    YellowFlag = 2,
    BlackFlag = 3,
    WhiteFlag = 4,
    CheckeredFlag = 5,
    PenaltyFlag = 6
}
