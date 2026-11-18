using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Pivoki.Core;

public sealed record PackageOutput(string Format, int MaxEdge, string RelativeDir);
public sealed record OutputPackage(string PackageId, int Revision, string Name, PackageOutput[] Outputs);
public sealed record PackagePlanRow(string Source, string Target, string Status, string? Reason);
public sealed record SkippedInput(string Source, string Reason);
public sealed record PackageJob(string JobId, string Name, string Directory, string[] Paths, string CreatedAt);
public sealed record PackageReply
{
    public required string Status { get; init; }
    public string? Error { get; init; }
    public string? Code { get; init; }
    public OutputPackage[] Packages { get; init; } = [];
    public OutputPackage? Package { get; init; }
    public string? PlanId { get; init; }
    public string? Directory { get; init; }
    public PackagePlanRow[] Rows { get; init; } = [];
    public SkippedInput[] Skipped { get; init; } = [];
    public string[] Paths { get; init; } = [];
    public PackageJob[] Jobs { get; init; } = [];
}

public static class PackageEngine
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    private static ProcessStartInfo StartInfo(string command)
    {
        var path = Environment.GetEnvironmentVariable("PIVOKI_ENGINE");
        if (string.IsNullOrWhiteSpace(path))
            path = Path.Combine(AppContext.BaseDirectory, "engine", "pivoki-engine.exe");
        if (!Path.IsPathFullyQualified(path) || !File.Exists(path))
            throw new FileNotFoundException("The Pivoki engine is missing. Use the complete app folder or set PIVOKI_ENGINE to its executable path.");
        var start = new ProcessStartInfo(path) { UseShellExecute = false, CreateNoWindow = true };
        start.ArgumentList.Add(command);
        return start;
    }

    public static void OpenStudio() => Process.Start(StartInfo("studio"))?.Dispose();

    public static async Task<PackageReply> RequestAsync(object request)
    {
        var start = StartInfo("rpc");
        start.RedirectStandardInput = start.RedirectStandardOutput = start.RedirectStandardError = true;
        start.StandardInputEncoding = new UTF8Encoding(false);
        start.StandardOutputEncoding = start.StandardErrorEncoding = Encoding.UTF8;
        using var process = Process.Start(start) ?? throw new IOException("The Pivoki engine could not start.");
        var output = process.StandardOutput.ReadToEndAsync();
        var errors = process.StandardError.ReadToEndAsync();
        await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(request, Json));
        process.StandardInput.Close();
        await process.WaitForExitAsync();
        var content = await output;
        var diagnostic = (await errors).Trim();
        if (content.Trim().Length == 0)
            throw new IOException(diagnostic.Length == 0 ? $"The engine exited with code {process.ExitCode}." : diagnostic);
        var result = JsonSerializer.Deserialize<PackageReply>(content, Json) ?? throw new InvalidDataException("The engine returned an empty reply.");
        if (result.Status == "failed" || (process.ExitCode != 0 && result.Status is not ("cancelled" or "skipped")))
            throw new InvalidOperationException(result.Error ?? $"The engine exited with code {process.ExitCode}.");
        return result;
    }
}
